/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class InboundFlow extends Component {
    static template = "stock_barcode_lite.InboundPage";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.barcodeInputRef = useRef("barcodeInput");

        this.state = useState({
            loading: false,
            message: "",
            messageType: "info",
            nextStep: "scan_picking",
            pallets: [],
            picking: null,
            currentLocation: {},
            summary: {
                total_pallets: 0,
                updated_pallets: 0,
                pending_pallets: 0,
                total_move_lines: 0,
                updated_move_lines: 0,
                pending_move_lines: 0,
            },
            lastScan: {},
            updatedMoveLineIds: [],
        });

        this._isProcessing = false;
        this._isPDA = this._detectPDA();
        this._isDestroyed = false;

        this._pendingTimers = [];
        this._messageTimer = null;
        this._confirmResetTimer = null;

        this._isFocusing = false;

        this._boundOnBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundOnBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundOnBarcodeBlur = this._onBarcodeBlur.bind(this);

        onMounted(async () => {
            this._bindVisibilityChange();

            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.addEventListener("input", this._boundOnBarcodeInput);
                barcodeInput.addEventListener("keydown", this._boundOnBarcodeKeydown);
                barcodeInput.addEventListener("blur", this._boundOnBarcodeBlur);
                this._focusBarcodeInput();
            }

            await this._initScanState();
        });

        onWillUnmount(() => {
            this._isDestroyed = true;

            this._unbindVisibilityChange();

            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.removeEventListener("input", this._boundOnBarcodeInput);
                barcodeInput.removeEventListener("keydown", this._boundOnBarcodeKeydown);
                barcodeInput.removeEventListener("blur", this._boundOnBarcodeBlur);
            }

            for (const id of this._pendingTimers) {
                clearTimeout(id);
            }
            this._pendingTimers = [];
            this._messageTimer = null;
            this._confirmResetTimer = null;
        });
    }

    _safeSetTimeout(fn, delay) {
        if (this._isDestroyed) {
            return null;
        }

        const id = setTimeout(() => {
            const index = this._pendingTimers.indexOf(id);
            if (index !== -1) {
                this._pendingTimers.splice(index, 1);
            }

            if (!this._isDestroyed) {
                fn();
            }
        }, delay);

        this._pendingTimers.push(id);
        return id;
    }

    _clearSafeTimeout(id) {
        if (id === null || id === undefined) {
            return;
        }

        const index = this._pendingTimers.indexOf(id);
        if (index !== -1) {
            this._pendingTimers.splice(index, 1);
        }

        clearTimeout(id);
    }

    _detectPDA() {
        const hasFinePointer = window.matchMedia("(pointer: fine)").matches;
        const hasHover = window.matchMedia("(hover: hover)").matches;
        const isSmallScreen = window.matchMedia("(max-width: 768px)").matches;
        const hasTouchScreen =
            "ontouchstart" in window ||
            navigator.maxTouchPoints > 0 ||
            window.matchMedia("(pointer: coarse)").matches;

        return isSmallScreen && hasTouchScreen && !hasFinePointer && !hasHover;
    }

    _onBarcodeInput(ev) {
        const input = ev.target;
        if (!input) {
            return;
        }

        const value = input.value;

        if (
            ev.inputType === "insertLineFeed" ||
            value.includes("\n") ||
            value.includes("\r")
        ) {
            const barcode = value.replace(/\n/g, "").replace(/\r/g, "").trim();
            if (barcode) {
                input.value = "";
                this.onBarcodeScanned(barcode);
            }
        }
    }

    _onBarcodeKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }

        ev.preventDefault();

        const input = ev.target;
        const barcode = input.value.trim();

        if (barcode) {
            input.value = "";
            this.onBarcodeScanned(barcode);
        }
    }

    _onBarcodeBlur() {
        if (this._isDestroyed || this._isProcessing || this._isFocusing) {
            return;
        }

        this._isFocusing = true;

        this._safeSetTimeout(() => {
            this._isFocusing = false;

            if (!this._isDestroyed) {
                this._focusBarcodeInput();
            }
        }, 0);
    }

    _focusBarcodeInput() {
        if (this._isDestroyed) {
            return;
        }

        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
        }
    }

    _bindVisibilityChange() {
        this._onVisibilityChange = () => {
            if (
                !this._isDestroyed &&
                document.visibilityState === "visible"
            ) {
                this._focusBarcodeInput();
            }
        };

        document.addEventListener("visibilitychange", this._onVisibilityChange);
    }

    _unbindVisibilityChange() {
        if (this._onVisibilityChange) {
            document.removeEventListener(
                "visibilitychange",
                this._onVisibilityChange
            );
            this._onVisibilityChange = null;
        }
    }

    async _initScanState() {
        const context = this.props?.action?.context || {};
        const pickingId = context.pickingId || context.picking_id || false;
        const currentLocationId =
            context.currentLocationId || context.current_location_id || false;

        if (!pickingId) {
            this.state.nextStep = "scan_picking";
            return;
        }

        this._isProcessing = true;

        try {
            this.state.loading = true;

            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "get_incoming_scan_state",
                [pickingId, currentLocationId || false, {}]
            );

            if (this._isDestroyed) {
                return;
            }

            const scanState = result?.scan_state || result || {};
            const nextStep =
                result?.next_step ||
                (scanState.picking?.state === "done"
                    ? "completed"
                    : scanState.picking?.id
                      ? scanState.current_location?.id
                          ? "scan_package"
                          : "scan_location"
                      : "scan_picking");

            await this._applyScanResult(
                {
                    scan_state: scanState,
                    next_step: nextStep,
                },
                false
            );
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
            }
            this._isProcessing = false;
        }
    }

    async onBarcodeScanned(barcode) {
        if (
            !barcode ||
            this._isDestroyed ||
            this.state.loading ||
            this._isProcessing
        ) {
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;

        try {
            const pickingId = this.state.picking?.id || false;
            const locationId = this.state.currentLocation?.id || false;

            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_incoming_scan_barcode",
                [barcode, pickingId, locationId]
            );

            if (this._isDestroyed) {
                return;
            }

            await this._applyScanResult(result, true);

            if (result?.action?.updated_move_line_ids?.length) {
                this.state.updatedMoveLineIds =
                    result.action.updated_move_line_ids;
            }
        } catch (error) {
            if (!this._isDestroyed) {
                console.error("[InboundFlow] scan error:", error);
                this.showMessage(this.formatError(error), "danger");
                this._flashScreen([200, 100, 100], true);
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
            this._isProcessing = false;
        }
    }

    async _applyScanResult(result, notify = true) {
        if (!result || this._isDestroyed) {
            return;
        }

        const scanState = result.scan_state || result || {};
        const derivedNextStep =
            scanState.picking?.state === "done"
                ? "completed"
                : scanState.picking?.id
                  ? scanState.current_location?.id
                      ? "scan_package"
                      : "scan_location"
                  : "scan_picking";

        this.state.picking = scanState.picking?.id
            ? { ...scanState.picking }
            : null;

        this.state.currentLocation = scanState.current_location?.id
            ? { ...scanState.current_location }
            : {};

        this.state.summary = scanState.summary
            ? { ...scanState.summary }
            : this._getEmptySummary();

        if (Array.isArray(scanState.pallets) && scanState.pallets.length) {
            this.state.pallets = scanState.pallets.map((pallet) => ({
                ...pallet,
                products: Array.isArray(pallet.products)
                    ? pallet.products.map((product) => ({ ...product }))
                    : [],
            }));
        } else {
            this.state.pallets = [];
        }

        this.state.lastScan = scanState.last_scan
            ? { ...scanState.last_scan }
            : {};

        this.state.nextStep = result.next_step || derivedNextStep;

        if (notify && result.message) {
            const messageType =
                result.success === false ? "danger" : "success";

            this.showMessage(result.message, messageType);

            if (result.success !== false) {
                this._flashScreen([100, 200, 100], false);
            }
        }
    }

    _getEmptySummary() {
        return {
            total_pallets: 0,
            updated_pallets: 0,
            pending_pallets: 0,
            total_move_lines: 0,
            updated_move_lines: 0,
            pending_move_lines: 0,
        };
    }

    async confirmInbound() {
        if (!this.state.picking?.id) {
            this.showMessage(_t("No picking loaded"), "danger");
            return;
        }

        if (this.state.loading || this._isProcessing) {
            return;
        }

        if (this.state.summary.pending_pallets > 0) {
            this.showMessage(
                _t("There are still ") +
                    this.state.summary.pending_pallets +
                    _t(" pallet(s) not updated"),
                "danger"
            );
            return;
        }

        if (this.state.nextStep === "completed") {
            this.showMessage(
                _t(
                    "Incoming picking is already completed. Cannot confirm again."
                ),
                "danger"
            );
            return;
        }

        const pickingId = this.state.picking.id;
        this._isProcessing = true;
        this.state.loading = true;

        try {
            const result = await this.orm.call(
                "stock.picking",
                "button_validate",
                [[pickingId]]
            );

            if (this._isDestroyed) {
                return;
            }

            if (result?.type) {
                await this.action.doAction(result);
                return;
            }

            this.showMessage(
                _t("Inbound confirmed successfully!"),
                "success"
            );
            this._flashScreen([100, 300, 100], true);

            this._confirmResetTimer = this._safeSetTimeout(() => {
                this._confirmResetTimer = null;

                if (
                    !this._isDestroyed &&
                    this.state.picking?.id === pickingId
                ) {
                    this.resetScan();
                }
            }, 2000);
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
            }
            this._isProcessing = false;
        }
    }

    resetScan() {
        this._clearSafeTimeout(this._confirmResetTimer);
        this._confirmResetTimer = null;

        this.state.picking = null;
        this.state.currentLocation = {};
        this.state.summary = this._getEmptySummary();
        this.state.pallets = [];
        this.state.lastScan = {};
        this.state.updatedMoveLineIds = [];
        this.state.nextStep = "scan_picking";

        this.showMessage(
            _t("Scan reset - ready for new picking"),
            "info"
        );

        this._focusBarcodeInput();
    }

    exit() {
        this.action.doAction("stock_barcode_lite_homepage");
    }

    showMessage(text, type = "info") {
        if (this._isDestroyed) {
            return;
        }

        this.state.message = text;
        this.state.messageType = type;

        this._clearSafeTimeout(this._messageTimer);
        this._messageTimer = null;

        if (type !== "danger") {
            this._messageTimer = this._safeSetTimeout(() => {
                this._messageTimer = null;

                if (
                    !this._isDestroyed &&
                    this.state.message === text
                ) {
                    this.state.message = "";
                }
            }, 4000);
        }
    }

    _flashScreen(pattern, repeat) {
        if (!("vibrate" in navigator)) {
            return;
        }

        try {
            navigator.vibrate(repeat ? pattern : 100);
        } catch (error) {
            console.warn("[InboundFlow] vibrate failed:", error);
        }
    }

    formatError(err) {
        return (
            err?.data?.arguments?.[0] ||
            (err?.data?.message
                ? err.data.message.replace(
                      /^odoo\.exceptions\.[^:]+:\s*/,
                      ""
                  )
                : "") ||
            err?.message ||
            _t("Unknown error")
        );
    }

    get hasPicking() {
        return !!this.state.picking?.id;
    }

    get hasLocation() {
        return !!this.state.currentLocation?.id;
    }

    get pickingLabel() {
        return this.state.picking?.name || "";
    }

    get pickingOrigin() {
        return this.state.picking?.origin || "";
    }

    get pickingReference() {
        return this.state.picking?.reference || "";
    }

    get pickingPartner() {
        return this.state.picking?.partner || "";
    }

    get pickingState() {
        return this.state.picking?.state || "";
    }

    get currentLocationName() {
        return (
            this.state.currentLocation?.display_name ||
            this.state.currentLocation?.name ||
            ""
        );
    }

    get currentLocationBarcode() {
        return this.state.currentLocation?.barcode || "";
    }

    get isScanPickingStep() {
        return this.state.nextStep === "scan_picking";
    }

    get isScanLocationStep() {
        return this.state.nextStep === "scan_location";
    }

    get isScanPackageStep() {
        return this.state.nextStep === "scan_package";
    }

    get scanModeLabel() {
        const map = {
            scan_picking: _t("Scan incoming picking"),
            scan_location: _t("Scan location"),
            scan_package: _t("Scan pallet"),
        };

        return map[this.state.nextStep] || _t("Scan barcode");
    }

    get stepHint() {
        const hints = {
            scan_picking: _t("Scan the incoming picking barcode to start"),
            scan_location: _t("Scan a storage location barcode"),
            scan_package: _t(
                "Scan a pallet barcode to update its location"
            ),
        };

        return hints[this.state.nextStep] || "";
    }

    get summaryCards() {
        const summary = this.state.summary || {};

        return [
            {
                key: "total_pallets",
                label: _t("Total Pallets"),
                value: summary.total_pallets || 0,
                icon: "fa-cubes",
            },
            {
                key: "updated_pallets",
                label: _t("Updated"),
                value: summary.updated_pallets || 0,
                icon: "fa-check-circle",
                class: "text-success",
            },
            {
                key: "pending_pallets",
                label: _t("Pending"),
                value: summary.pending_pallets || 0,
                icon: "fa-clock",
                class: "text-warning",
            },
            {
                key: "total_move_lines",
                label: _t("Move Lines"),
                value: summary.total_move_lines || 0,
                icon: "fa-arrows-alt-v",
            },
            {
                key: "updated_move_lines",
                label: _t("Processed"),
                value: summary.updated_move_lines || 0,
                icon: "fa-check",
                class: "text-success",
            },
            {
                key: "pending_move_lines",
                label: _t("Remaining"),
                value: summary.pending_move_lines || 0,
                icon: "fa-hourglass-half",
                class: "text-warning",
            },
        ];
    }

    get progressPercent() {
        const summary = this.state.summary || {};
        const total = summary.total_move_lines || 0;
        const done = summary.updated_move_lines || 0;

        if (!total) {
            return 0;
        }

        return Math.round((done / total) * 100);
    }

    get isAllComplete() {
        return (
            (this.state.summary?.pending_pallets || 0) === 0 &&
            (this.state.summary?.total_pallets || 0) > 0
        );
    }

    get palletList() {
        return Array.isArray(this.state.pallets) ? this.state.pallets : [];
    }

    getStateBadgeClass(state) {
        const map = {
            draft: "bg-secondary",
            waiting: "bg-warning text-dark",
            confirmed: "bg-info",
            assigned: "bg-primary",
            done: "bg-success",
            cancel: "bg-danger",
        };

        return map[state] || "bg-secondary";
    }

    getStateLabel(state) {
        const map = {
            draft: _t("Draft"),
            waiting: _t("Waiting"),
            confirmed: _t("Confirmed"),
            assigned: _t("Ready"),
            done: _t("Done"),
            cancel: _t("Cancelled"),
        };

        return map[state] || state;
    }
}