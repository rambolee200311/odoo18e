/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const MAX_QUEUED_BARCODES = 20;

export class VasOutboundPalletizationDialog extends Component {
    static template = "wd_warehouse_value_add.VasOutboundPalletizationDialog";
    static props = {
        mode: String,
        orderId: Number,
        onClose: Function,
        onOrderUpdated: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.barcodeInputRef = useRef("palletizationBarcodeInput");
        this._isDestroyed = false;
        this._pendingBarcodes = [];
        this._isDrainingBarcodeQueue = false;
        this._scanInputStarted = false;
        this._scanInputIdleTimer = null;
        this.state = useState({
            palletizationId: null,
            palletizationResult: null,
            palletizationModalOpen: this.props.mode === "manage",
            createPalletModalOpen: this.props.mode === "create",
            palletCount: 1,
            palletizationInput: "",
            palletizationEditLineId: null,
            palletizationEditQuantity: 0,
            destinationPalletsExpanded: true,
            unassignedExpanded: false,
            busy: false,
            loading: this.props.mode === "manage",
            errorMessage: "",
            scanErrorMessage: "",
        });

        this._boundBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundBarcodeBlur = this._onBarcodeBlur.bind(this);
        this._boundDocumentKeydown = this._onDocumentKeydown.bind(this);
        this._boundWindowFocus = this._onWindowFocus.bind(this);
        this._boundVisibilityChange = this._onDocumentVisibilityChange.bind(this);

        onMounted(() => {
            const input = this.barcodeInputRef.el;
            if (input) {
                input.addEventListener("input", this._boundBarcodeInput);
                input.addEventListener("keydown", this._boundBarcodeKeydown);
                input.addEventListener("blur", this._boundBarcodeBlur);
            }
            document.addEventListener("keydown", this._boundDocumentKeydown, true);
            window.addEventListener("focus", this._boundWindowFocus);
            document.addEventListener("visibilitychange", this._boundVisibilityChange);
            this._scannerLog("component-mounted");
            this._reconcileFocus("component-mounted");
            if (this.props.mode === "manage") {
                this.startOutboundPalletization();
            }
        });

        onWillUnmount(() => {
            this._isDestroyed = true;
            const input = this.barcodeInputRef.el;
            if (input) {
                input.removeEventListener("input", this._boundBarcodeInput);
                input.removeEventListener("keydown", this._boundBarcodeKeydown);
                input.removeEventListener("blur", this._boundBarcodeBlur);
            }
            document.removeEventListener("keydown", this._boundDocumentKeydown, true);
            window.removeEventListener("focus", this._boundWindowFocus);
            document.removeEventListener("visibilitychange", this._boundVisibilityChange);
            clearTimeout(this._scanInputIdleTimer);
            this._scannerLog("component-unmounted");
        });
    }

    get palletizationScanState() {
        return this.state.palletizationResult?.scan_state || {};
    }

    get palletizationCurrent() {
        return this.state.palletizationResult?.current || {};
    }

    get palletizationNextStep() {
        return this.state.palletizationResult?.next_step || "scan_destination";
    }

    get isPalletizationBarcodeStep() {
        return ["scan_destination", "scan_source", "scan_product", "scan_lot", "scan_serial"].includes(
            this.palletizationNextStep
        );
    }

    get isPalletizationQuantityStep() {
        return this.palletizationNextStep === "input_quantity";
    }

    get palletizationStepIndex() {
        if (this.palletizationIsValidated) {
            return 4;
        }
        if (this.palletizationNextStep === "scan_destination") {
            return 1;
        }
        if (
            Number(this.palletizationScanState.summary?.unassigned_quantity || 0) <= 0 &&
            this.hasPalletizationAllocations
        ) {
            return 3;
        }
        return 2;
    }

    get palletizationPrompt() {
        return {
            scan_destination: _t("Select a destination transport pallet or scan its barcode with the PDA trigger."),
            scan_source: _t("Scan a source pallet or loose product with the PDA trigger."),
            scan_product: _t("Scan a product from the selected source with the PDA trigger."),
            scan_lot: _t("Scan a lot number with the PDA trigger."),
            scan_serial: _t("Scan a serial number with the PDA trigger."),
            input_quantity: _t("Enter the quantity to assign."),
            choose_whole_handling: _t("Choose how to handle this whole pallet."),
            validated: _t("Palletization is validated."),
        }[this.palletizationNextStep] || _t("Continue palletization.");
    }

    get palletizationIsValidated() {
        return this.palletizationScanState.palletization?.state === "validated";
    }

    get destinationTransportPallets() {
        return (this.palletizationScanState.transport_pallets || []).filter(
            (pallet) => pallet.is_transport_pallet
        );
    }

    get hasPalletizationAllocations() {
        return this.allocatedTransportPallets.length > 0;
    }

    get allocatedTransportPallets() {
        return (this.palletizationScanState.transport_pallets || []).filter(
            (pallet) => (pallet.product_lines || []).length > 0
        );
    }

    _scannerLog(event, details = {}) {
        const input = this.barcodeInputRef.el;
        const activeElement = document.activeElement;
        const activeElementName = activeElement
            ? `${activeElement.tagName?.toLowerCase() || "unknown"}${activeElement.id ? `#${activeElement.id}` : ""}`
            : null;
        console.info("[VAS palletization scanner]", event, {
            step: this.palletizationNextStep,
            busy: this.state.busy,
            modalOpen: this.state.palletizationModalOpen,
            inputExists: Boolean(input),
            inputDisabled: input?.disabled ?? null,
            inputFocused: Boolean(input && activeElement === input),
            activeElement: activeElementName,
            visibility: document.visibilityState,
            queuedScans: this._pendingBarcodes.length,
            ...details,
        });
    }

    _onBarcodeInput(event) {
        const input = event.target;
        if (!input || !this.state.palletizationModalOpen || !this.isPalletizationBarcodeStep) {
            return;
        }
        const value = input.value || "";
        if (value && !this._scanInputStarted) {
            this._scanInputStarted = true;
            this._scannerLog("input-started", {
                inputType: event.inputType || "unknown",
                inputLength: value.length,
            });
        }
        if (value) {
            clearTimeout(this._scanInputIdleTimer);
            this._scanInputIdleTimer = setTimeout(() => {
                this._scanInputStarted = false;
                this._scannerLog("input-idle-without-terminator", {
                    inputLength: input.value?.length || 0,
                });
            }, 1000);
        }
        if (event.inputType === "insertLineFeed" || value.includes("\n") || value.includes("\r")) {
            this._consumeBarcode(input);
        }
    }

    _onBarcodeKeydown(event) {
        if (event.key !== "Enter") {
            return;
        }
        event.preventDefault();
        const input = event.target;
        this._scannerLog("enter-key", { inputLength: input?.value?.length || 0 });
        if (this.state.palletizationModalOpen && this.isPalletizationBarcodeStep) {
            this._consumeBarcode(input);
        } else if (input) {
            input.value = "";
        }
    }

    _onBarcodeBlur() {
        if (this.state.palletizationModalOpen && this.isPalletizationBarcodeStep) {
            this._scannerLog("scanner-input-blurred");
            if (this.state.palletizationEditLineId) {
                this._scannerLog("scanner-focus-yielded-to-allocation-editor");
                return;
            }
            this._reconcileFocus("scanner-input-blurred");
        }
    }

    _onWindowFocus() {
        this._scannerLog("window-focused");
        this._reconcileFocus("window-focused");
    }

    _onDocumentKeydown(event) {
        if (
            !this.state.palletizationModalOpen ||
            !this.isPalletizationBarcodeStep ||
            event.target === this.barcodeInputRef.el
        ) {
            return;
        }
        this._scannerLog("keydown-outside-scanner-input", {
            key: event.key === "Enter" ? "Enter" : "character",
            targetTag: event.target?.tagName?.toLowerCase() || "unknown",
            targetId: event.target?.id || null,
        });
    }

    _onDocumentVisibilityChange() {
        this._scannerLog("document-visibility-changed");
        if (document.visibilityState === "visible") {
            this._reconcileFocus("document-visible");
        }
    }

    _consumeBarcode(input) {
        const barcode = (input?.value || "").replace(/[\r\n]/g, "").trim();
        clearTimeout(this._scanInputIdleTimer);
        this._scanInputStarted = false;
        if (input) {
            input.value = "";
        }
        if (!barcode) {
            this._scannerLog("empty-scan-terminator");
            return;
        }
        this._scannerLog("barcode-captured", { barcodeLength: barcode.length });
        if (this.state.busy || this._isDrainingBarcodeQueue) {
            if (this._pendingBarcodes.length >= MAX_QUEUED_BARCODES) {
                this._scannerLog("barcode-queue-full", { barcodeLength: barcode.length });
                this.notification.add(_t("Too many scans are queued. Wait for processing to finish before scanning again."), { type: "warning" });
                return;
            }
            this._pendingBarcodes.push(barcode);
            this._scannerLog("barcode-queued", { barcodeLength: barcode.length });
            return;
        }
        this.submitPalletizationInput(barcode);
    }

    _reconcileFocus(reason = "state-change") {
        if (this._isDestroyed) {
            return;
        }
        this._scannerLog("focus-reconcile-scheduled", { reason });
        requestAnimationFrame(() => {
            if (this._isDestroyed || !this.state.palletizationModalOpen) {
                this._scannerLog("focus-reconcile-skipped", { reason, skipReason: "modal-closed-or-destroyed" });
                return;
            }
            if (this.state.palletizationEditLineId) {
                const allocationInput = this.el?.querySelector(".o_wd_vas_pallet-allocation-edit-input");
                if (!this.state.busy) {
                    allocationInput?.focus();
                }
                this._scannerLog("allocation-editor-focus-reconciled", {
                    reason,
                    allocationInputExists: Boolean(allocationInput),
                    allocationInputDisabled: allocationInput?.disabled ?? null,
                });
            } else if (this.isPalletizationQuantityStep) {
                const quantityInput = this.el?.querySelector(".o_wd_vas_palletization-quantity-input");
                if (!this.state.busy) {
                    quantityInput?.focus();
                }
                this._scannerLog("quantity-focus-reconciled", {
                    reason,
                    quantityInputExists: Boolean(quantityInput),
                    quantityInputDisabled: quantityInput?.disabled ?? null,
                });
            } else if (this.isPalletizationBarcodeStep) {
                const input = this.barcodeInputRef.el;
                if (input) {
                    if (document.activeElement !== input) {
                        input.focus();
                    }
                    this._scannerLog("barcode-focus-reconciled", { reason });
                } else {
                    this._scannerLog("barcode-focus-failed", { reason, failure: "input-not-found" });
                }
            } else {
                if (document.activeElement === this.barcodeInputRef.el) {
                    this.barcodeInputRef.el?.blur();
                }
                this._scannerLog("barcode-focus-not-required", { reason });
            }
        });
    }

    _finishBusyAction(reason) {
        this.state.busy = false;
        this._reconcileFocus(reason);
        void this._drainQueuedBarcodes();
    }

    async _drainQueuedBarcodes() {
        if (
            this._isDestroyed ||
            this._isDrainingBarcodeQueue ||
            this.state.busy ||
            !this.state.palletizationModalOpen ||
            !this._pendingBarcodes.length
        ) {
            return;
        }
        if (!this.state.palletizationId) {
            return;
        }
        if (this.palletizationNextStep === "choose_whole_handling") {
            this._scannerLog("barcode-queue-waiting-for-whole-pallet-choice");
            return;
        }
        if (!this.isPalletizationBarcodeStep) {
            const count = this._pendingBarcodes.length;
            this._pendingBarcodes = [];
            this._scannerLog("barcode-queue-cleared-for-non-scan-step", { clearedScans: count });
            this.notification.add(
                _t("Queued scans were cleared because the current step requires a manual action. Please scan again after completing it."),
                { type: "warning" }
            );
            return;
        }

        this._isDrainingBarcodeQueue = true;
        try {
            while (
                !this._isDestroyed &&
                this.state.palletizationModalOpen &&
                !this.state.busy &&
                this._pendingBarcodes.length &&
                this.isPalletizationBarcodeStep
            ) {
                const barcode = this._pendingBarcodes.shift();
                this._scannerLog("queued-barcode-processing", { barcodeLength: barcode.length });
                await this.submitPalletizationInput(barcode);
            }
        } catch (error) {
            this._scannerLog("queued-barcode-processing-failed", {
                error: error.data?.arguments?.[0] || error.message || "unknown error",
            });
            this._clearQueuedBarcodes("queued-scan-error");
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Queued scans could not be processed."), { type: "danger" });
        } finally {
            this._isDrainingBarcodeQueue = false;
            if (this._pendingBarcodes.length && !this.state.busy) {
                void this._drainQueuedBarcodes();
            }
        }
    }

    _clearQueuedBarcodes(reason) {
        if (this._pendingBarcodes.length) {
            this._scannerLog("barcode-queue-cleared", {
                reason,
                clearedScans: this._pendingBarcodes.length,
            });
            this._pendingBarcodes = [];
        }
    }

    async startOutboundPalletization() {
        if (!this.props.orderId || this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.loading = true;
        this.state.errorMessage = "";
        try {
            const result = await this.orm.call(
                "wd.vas.order",
                "action_start_outbound_palletization",
                [[this.props.orderId]]
            );
            await this.refreshPalletizationState(result.palletization_id);
            this.state.unassignedExpanded = false;
        } catch (error) {
            this.state.errorMessage = error.data?.arguments?.[0] || error.message || _t("Palletization could not be started.");
            this.notification.add(this.state.errorMessage, { type: "danger" });
            this._clearQueuedBarcodes("palletization-start-failed");
        } finally {
            this.state.loading = false;
            this._finishBusyAction("palletization-start-finished");
        }
    }

    async confirmCreateTransportPallets() {
        const palletCount = Number(this.state.palletCount);
        if (!Number.isInteger(palletCount) || palletCount <= 0) {
            this.notification.add(_t("Enter a valid transport pallet quantity greater than zero."), { type: "warning" });
            return;
        }
        if (!this.props.orderId || this.state.busy) {
            return;
        }

        this.state.busy = true;
        let closeAfterCreate = false;
        try {
            const started = await this.orm.call(
                "wd.vas.order",
                "action_start_outbound_palletization",
                [[this.props.orderId]]
            );
            await this.orm.call(
                "wd.vas.outbound.palletization",
                "action_create_transport_pallets",
                [[started.palletization_id], palletCount]
            );

            closeAfterCreate = true;
            this.state.palletizationId = started.palletization_id;
            let palletListLoaded = false;
            let workOrderReloaded = false;
            try {
                await this.refreshPalletizationState(started.palletization_id);
                palletListLoaded = true;
            } catch (error) {
                const details = error.data?.arguments?.[0] || error.message;
                this.notification.add(
                    details
                        ? _t("Transport pallets were created, but the pallet list could not be refreshed. Use Enter Palletization to reload it. Details: ") + details
                        : _t("Transport pallets were created, but the pallet list could not be refreshed. Use Enter Palletization to reload it."),
                    { type: "warning" }
                );
            }
            try {
                await this.props.onOrderUpdated();
                workOrderReloaded = true;
            } catch (error) {
                const details = error.data?.arguments?.[0] || error.message;
                this.notification.add(
                    details
                        ? _t("Transport pallets were created and loaded, but the work order view could not be refreshed. Details: ") + details
                        : _t("Transport pallets were created and loaded, but the work order view could not be refreshed."),
                    { type: "warning" }
                );
            }
            if (palletListLoaded && workOrderReloaded) {
                this.notification.add(_t("Transport pallets created and ready for palletization."), { type: "success" });
            }
        } catch (error) {
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Transport pallets could not be created."), { type: "danger" });
        } finally {
            this.state.busy = false;
            if (closeAfterCreate) {
                this._clearQueuedBarcodes("create-dialog-closed");
                this.props.onClose();
            }
        }
    }

    async refreshPalletizationState(palletizationId) {
        const result = await this.orm.call(
            "stock.barcode.lite.scan.service",
            "get_vas_outbound_palletization_scan_state",
            [palletizationId]
        );
        this.state.palletizationId = palletizationId;
        this.state.palletizationResult = result;
        this.state.palletizationInput = "";
        this.state.palletizationEditLineId = null;
        return result;
    }

    async callPalletizationService(method, args) {
        const result = await this.orm.call("stock.barcode.lite.scan.service", method, args);
        this.state.palletizationResult = result;
        this.state.palletizationInput = "";
        if (!result.success) {
            this.state.scanErrorMessage = result.message || _t("Palletization action failed.");
        } else {
            this.state.scanErrorMessage = "";
        }
        return result;
    }

    onPalletizationInputKeydown(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            this.submitPalletizationInput();
        }
    }

    async submitPalletizationInput(rawValue) {
        const value = typeof rawValue === "string" || typeof rawValue === "number"
            ? rawValue
            : this.state.palletizationInput;
        const code = String(value ?? "").trim();
        const palletizationId = this.state.palletizationId;
        const current = this.palletizationCurrent;
        if (!code || !palletizationId || this.state.busy || this.palletizationIsValidated) {
            this._scannerLog("scan-not-submitted", {
                barcodeLength: code.length,
                reason: !code
                    ? "empty-code"
                    : !palletizationId
                      ? "palletization-not-ready"
                      : this.state.busy
                        ? "busy"
                        : "already-validated",
            });
            return;
        }
        if (this.palletizationNextStep === "choose_whole_handling" || this.palletizationNextStep === "validated") {
            this._scannerLog("scan-not-submitted", {
                barcodeLength: code.length,
                reason: this.palletizationNextStep,
            });
            return;
        }

        let method;
        let args;
        switch (this.palletizationNextStep) {
            case "scan_destination":
                method = "process_vas_outbound_palletization_destination_scan";
                args = [code, palletizationId];
                break;
            case "scan_source":
                method = "process_vas_outbound_palletization_source_scan";
                args = [code, palletizationId, current.destination_package_id || false];
                break;
            case "scan_product":
                method = "process_vas_outbound_palletization_product_scan";
                args = [code, palletizationId, current.source_package_id || false, current.destination_package_id || false];
                break;
            case "scan_lot":
            case "scan_serial":
                method = "process_vas_outbound_palletization_lot_scan";
                args = [code, palletizationId, current.source_package_id || false, current.product_id || false, current.destination_package_id || false];
                break;
            case "input_quantity": {
                const quantity = Number(code);
                if (!Number.isFinite(quantity) || quantity <= 0) {
                    this.notification.add(_t("Enter a valid quantity greater than zero."), { type: "warning" });
                    return;
                }
                method = "process_vas_outbound_palletization_quantity";
                args = [palletizationId, current.source_package_id || false, current.product_id || false, current.lot_id || false, quantity, current.destination_package_id || false];
                break;
            }
            default:
                return;
        }

        this.state.busy = true;
        this._scannerLog("scan-request-started", {
            method,
            barcodeLength: code.length,
        });
        try {
            const result = await this.callPalletizationService(method, args);
            this._scannerLog("scan-request-finished", {
                method,
                success: Boolean(result.success),
                nextStep: result.next_step || this.palletizationNextStep,
            });
        } catch (error) {
            const message = error.data?.arguments?.[0] || error.message || _t("Palletization scan failed.");
            this._scannerLog("scan-request-failed", { method, error: message });
            this.state.scanErrorMessage = message;
        } finally {
            this._finishBusyAction("scan-request-finished");
        }
    }

    async selectDestinationPallet(pallet) {
        if (!pallet?.barcode || !this.state.palletizationId || this.state.busy || this.palletizationIsValidated) {
            return;
        }
        this.state.busy = true;
        try {
            await this.callPalletizationService(
                "process_vas_outbound_palletization_destination_scan",
                [pallet.barcode, this.state.palletizationId]
            );
        } catch (error) {
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Destination pallet could not be selected."), { type: "danger" });
        } finally {
            this._finishBusyAction("destination-pallet-selection-finished");
        }
    }

    async handleWholePallet(handlingType) {
        const palletizationId = this.state.palletizationId;
        const current = this.palletizationCurrent;
        if (!palletizationId || !current.source_package_id || this.state.busy || this.palletizationIsValidated) {
            return;
        }
        const method = handlingType === "direct_outbound"
            ? "action_vas_outbound_palletization_direct"
            : "action_vas_outbound_palletization_group_whole";
        const args = handlingType === "direct_outbound"
            ? [palletizationId, current.source_package_id, current.destination_package_id || false]
            : [palletizationId, current.source_package_id, false, current.destination_package_id || false];
        this.state.busy = true;
        try {
            await this.callPalletizationService(method, args);
        } catch (error) {
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Whole pallet could not be assigned."), { type: "danger" });
        } finally {
            this._finishBusyAction("whole-pallet-action-finished");
        }
    }

    startAllocationEdit(allocation, productTracking) {
        if (this.state.busy || this.palletizationIsValidated || productTracking === "serial") {
            return;
        }
        this.state.palletizationEditLineId = allocation.id;
        this.state.palletizationEditQuantity = allocation.quantity;
        this._reconcileFocus("allocation-edit-started");
    }

    cancelAllocationEdit() {
        this.state.palletizationEditLineId = null;
        this._reconcileFocus("allocation-edit-cancelled");
    }

    async saveAllocationEdit(pallet, allocation, productTracking) {
        if (productTracking === "serial") {
            return;
        }
        const quantity = Number(this.state.palletizationEditQuantity);
        if (!Number.isFinite(quantity) || quantity <= 0) {
            this.notification.add(_t("Enter a valid quantity greater than zero."), { type: "warning" });
            return;
        }
        const handlingType = allocation.handling_type;
        this.state.busy = true;
        try {
            const result = await this.callPalletizationService(
                "update_vas_outbound_palletization_line",
                [this.state.palletizationId, allocation.id, quantity, handlingType, false, pallet.id]
            );
            if (result.success) {
                this.state.palletizationEditLineId = null;
            }
        } catch (error) {
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Allocation could not be updated."), { type: "danger" });
        } finally {
            this._finishBusyAction("allocation-update-finished");
        }
    }

    async removeAllocation(pallet, allocation) {
        if (this.state.busy || this.palletizationIsValidated) {
            return;
        }
        this.state.busy = true;
        try {
            await this.callPalletizationService(
                "remove_vas_outbound_palletization_allocations",
                [this.state.palletizationId, pallet.id, [allocation.id]]
            );
        } catch (error) {
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Allocation could not be removed."), { type: "danger" });
        } finally {
            this._finishBusyAction("allocation-removal-finished");
        }
    }

    async validatePalletization() {
        if (!this.state.palletizationId || this.state.busy || this.palletizationIsValidated) {
            return;
        }
        this.state.busy = true;
        try {
            await this.callPalletizationService(
                "action_validate_vas_outbound_palletization",
                [this.state.palletizationId]
            );
        } catch (error) {
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Palletization could not be validated."), { type: "danger" });
        } finally {
            this._finishBusyAction("palletization-validation-finished");
        }
    }

    closeDialog() {
        if (!this.state.busy) {
            this._clearQueuedBarcodes("dialog-closed");
            this.props.onClose();
        }
    }

    toggleUnassignedGoods() {
        this.state.unassignedExpanded = !this.state.unassignedExpanded;
    }

    toggleDestinationPallets() {
        this.state.destinationPalletsExpanded = !this.state.destinationPalletsExpanded;
    }

    dismissScanError() {
        this.state.scanErrorMessage = "";
    }
}
