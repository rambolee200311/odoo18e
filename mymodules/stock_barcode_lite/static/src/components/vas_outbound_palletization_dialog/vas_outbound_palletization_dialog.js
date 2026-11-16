/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

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
        });

        this._boundBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundBarcodeBlur = this._onBarcodeBlur.bind(this);

        onMounted(() => {
            const input = this.barcodeInputRef.el;
            if (input) {
                input.addEventListener("input", this._boundBarcodeInput);
                input.addEventListener("keydown", this._boundBarcodeKeydown);
                input.addEventListener("blur", this._boundBarcodeBlur);
            }
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
            scan_destination: _t("Select or scan a destination transport pallet."),
            scan_source: _t("Scan a source pallet or a loose product."),
            scan_product: _t("Scan a product from the selected source."),
            scan_lot: _t("Scan a lot number."),
            scan_serial: _t("Scan a serial number."),
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

    _onBarcodeInput(event) {
        const input = event.target;
        if (!input || !this.state.palletizationModalOpen || !this.isPalletizationBarcodeStep) {
            return;
        }
        const value = input.value || "";
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
        if (this.state.palletizationModalOpen && this.isPalletizationBarcodeStep) {
            this._consumeBarcode(input);
        } else if (input) {
            input.value = "";
        }
    }

    _onBarcodeBlur() {
        if (this.state.palletizationModalOpen && this.isPalletizationBarcodeStep) {
            this._reconcileFocus();
        }
    }

    _consumeBarcode(input) {
        const barcode = (input?.value || "").replace(/[\r\n]/g, "").trim();
        if (input) {
            input.value = "";
        }
        if (barcode) {
            this.submitPalletizationInput(barcode);
        }
    }

    _reconcileFocus() {
        if (this._isDestroyed) {
            return;
        }
        requestAnimationFrame(() => {
            if (this._isDestroyed || !this.state.palletizationModalOpen || this.state.busy) {
                return;
            }
            if (this.isPalletizationQuantityStep) {
                this.el?.querySelector(".o_wd_vas_palletization-quantity-input")?.focus();
            } else if (this.isPalletizationBarcodeStep) {
                const input = this.barcodeInputRef.el;
                if (input) {
                    input.focus();
                    input.value = "";
                }
            } else {
                this.barcodeInputRef.el?.blur();
            }
        });
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
        } finally {
            this.state.loading = false;
            this.state.busy = false;
            this._reconcileFocus();
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
            this.notification.add(result.message || _t("Palletization action failed."), { type: "danger" });
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
            return;
        }
        if (this.palletizationNextStep === "choose_whole_handling" || this.palletizationNextStep === "validated") {
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
        try {
            await this.callPalletizationService(method, args);
        } catch (error) {
            this.notification.add(error.data?.arguments?.[0] || error.message || _t("Palletization scan failed."), { type: "danger" });
        } finally {
            this.state.busy = false;
            this._reconcileFocus();
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
            this.state.busy = false;
            this._reconcileFocus();
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
            this.state.busy = false;
            this._reconcileFocus();
        }
    }

    startAllocationEdit(allocation) {
        if (this.state.busy || this.palletizationIsValidated) {
            return;
        }
        this.state.palletizationEditLineId = allocation.id;
        this.state.palletizationEditQuantity = allocation.quantity;
    }

    cancelAllocationEdit() {
        this.state.palletizationEditLineId = null;
    }

    async saveAllocationEdit(pallet, allocation) {
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
            this.state.busy = false;
            this._reconcileFocus();
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
            this.state.busy = false;
            this._reconcileFocus();
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
            this.state.busy = false;
            this._reconcileFocus();
        }
    }

    closeDialog() {
        if (!this.state.busy) {
            this.props.onClose();
        }
    }

    toggleUnassignedGoods() {
        this.state.unassignedExpanded = !this.state.unassignedExpanded;
    }

    toggleDestinationPallets() {
        this.state.destinationPalletsExpanded = !this.state.destinationPalletsExpanded;
    }
}
