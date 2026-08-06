/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

class InternalTransfer extends Component {
    static template = "stock_barcode_lite.InternalTransferPage";
    static props = {};

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.barcodeInputRef = useRef("barcodeInput");

        this.state = useState({
            loading: false,
            message: "",
            messageType: "info",
            nextStep: "scan_location",
            picking_id: null,
            picking_name: "",
            picking_origin: "",
            picking_state: "",
            destination_id: null,
            destination_name: "",
            scanned_packages: [],
            is_validating: false,
        });

        this._isProcessing = false;

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
        });

        onWillUnmount(() => {
            this._unbindVisibilityChange();
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.removeEventListener("input", this._boundOnBarcodeInput);
                barcodeInput.removeEventListener("keydown", this._boundOnBarcodeKeydown);
                barcodeInput.removeEventListener("blur", this._boundOnBarcodeBlur);
            }
        });

        const params = this.env.config.action?.params || {};

        if (params.message) {
            this.notification.add(params.message, { type: "success" });
        }

        if (params.picking_data) {
            this._initFromData(params.picking_data);
        } else if (params.picking_id) {
            this._loadPicking(params.picking_id);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 扫码监听
    // ═══════════════════════════════════════════════════════════════

    _onBarcodeInput(ev) {
        const input = ev.target;
        if (!input) return;

        const value = input.value;
        if (ev.inputType === "insertLineFeed" || value.includes("\n") || value.includes("\r")) {
            const barcode = value.replace(/\n/g, "").replace(/\r/g, "").trim();
            if (barcode) {
                input.value = "";
                this.onBarcodeScanned(barcode);
            }
        }
    }

    _onBarcodeKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const input = ev.target;
            const barcode = input.value.trim();
            if (barcode) {
                input.value = "";
                this.onBarcodeScanned(barcode);
            }
        }
    }

    _onBarcodeBlur(ev) {
        if (!this._isProcessing) {
            setTimeout(() => this._focusBarcodeInput(), 0);
        }
    }

    _focusBarcodeInput() {
        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
        }
    }

    _bindVisibilityChange() {
        this._onVisibilityChange = () => {
            if (document.visibilityState === "visible") {
                this._focusBarcodeInput();
            }
        };
        document.addEventListener("visibilitychange", this._onVisibilityChange);
    }

    _unbindVisibilityChange() {
        if (this._onVisibilityChange) {
            document.removeEventListener("visibilitychange", this._onVisibilityChange);
            this._onVisibilityChange = null;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 扫码核心
    // ═══════════════════════════════════════════════════════════════

    async onBarcodeScanned(barcode) {
        if (!barcode || this._isProcessing) {
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;

        try {
            if (this.state.nextStep === "scan_location") {
                await this._scanLocation(barcode);
            } else if (this.state.nextStep === "scan_package") {
                await this._scanPackage(barcode);
            }
        } catch (error) {
            console.error('[InternalTransfer] scan error:', error);
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._isProcessing = false;
            this._focusBarcodeInput();
        }
    }

    async _scanLocation(barcode) {
        const result = await this.orm.call("stock.picking", "action_scan_pda_destination_location", [
            this.state.picking_id, barcode
        ]);
        if (result.success) {
            this.state.destination_id = result.destination_location?.id;
            this.state.destination_name = result.destination_location?.name;
            this.state.scanned_packages = result.package_scan_lines?.map(line => ({
                id: line.id,
                name: line.package_name,
                barcode: line.barcode,
                location_name: line.source_location?.name || "",
                is_updated: false,
            })) || [];
            this.state.nextStep = "scan_package";
            this.showMessage(_t("Location scanned: ") + this.state.destination_name, "success");
            this._flashScreen([100, 200, 100], false);
        } else {
            this.showMessage(result.message || _t("Invalid location"), "danger");
            this._flashScreen([200, 100, 100], true);
        }
    }

    async _scanPackage(barcode) {
        const existing = this.state.scanned_packages.find(p => p.barcode === barcode);
        if (existing) {
            this.showMessage(_t("Package already scanned"), "warning");
            return;
        }

        const result = await this.orm.call("stock.picking", "action_scan_pda_package", [
            this.state.picking_id, barcode
        ]);
        if (result.success) {
            this.state.scanned_packages = [
                ...this.state.scanned_packages,
                {
                    id: result.package_line?.id,
                    name: result.package_line?.package_name || barcode,
                    barcode: barcode,
                    location_name: result.package_line?.source_location?.name || "",
                    is_updated: true,
                }
            ];
            this.showMessage(_t("Package scanned: ") + barcode, "success");
            this._flashScreen([100, 200, 100], false);
        } else {
            this.showMessage(result.message || _t("Invalid package"), "danger");
            this._flashScreen([200, 100, 100], true);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 初始化
    // ═══════════════════════════════════════════════════════════════

    _initFromData(data) {
        this.state.picking_id = data.picking_id;
        this.state.picking_name = data.picking_name;
        this.state.picking_origin = data.origin || "";
        this.state.picking_state = data.state || "assigned";
        this.state.nextStep = data.next_step === "scan_package" ? "scan_package" : "scan_location";
        this.state.destination_id = data.destination_location?.id || null;
        this.state.destination_name = data.destination_location?.name || "";
        this.state.scanned_packages = data.package_scan_lines?.map(line => ({
            id: line.id,
            name: line.package_name,
            barcode: line.barcode,
            location_name: line.source_location?.name || "",
            is_updated: false,
        })) || [];
    }

    async _loadPicking(picking_id) {
        try {
            this.state.loading = true;
            const data = await this.orm.call("stock.picking", "get_pda_internal_transfer_scan_data", [picking_id]);
            if (data) {
                this._initFromData(data);
            }
        } catch (error) {
            this.notification.add("Failed to load picking: " + error.message, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 操作按钮
    // ═══════════════════════════════════════════════════════════════

    async confirmTransfer() {
        if (!this.state.picking_id) {
            this.showMessage(_t("No transfer loaded"), "danger");
            return;
        }

        if (!this.state.destination_id) {
            this.showMessage(_t("Please scan destination location first"), "danger");
            return;
        }

        this.state.is_validating = true;
        this.state.loading = true;

        try {
            const result = await this.orm.call("stock.picking", "action_validate_pda_internal_transfer", [
                this.state.picking_id, this.state.destination_id,
                this.state.scanned_packages.map(p => p.id)
            ]);

            if (result.success) {
                this.showMessage(_t("Transfer confirmed successfully!"), "success");
                this._flashScreen([100, 300, 100], true);
                setTimeout(() => this._goHome(), 1500);
            } else {
                this.showMessage(result.message || _t("Validation failed"), "danger");
                this._flashScreen([200, 100, 100], true);
            }
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
        } finally {
            this.state.is_validating = false;
            this.state.loading = false;
        }
    }

    _onRemovePackage(packageId) {
        this.state.scanned_packages = this.state.scanned_packages.filter(p => p.id !== packageId);
    }

    _onClearDestination() {
        this.state.destination_id = null;
        this.state.destination_name = "";
        this.state.scanned_packages = [];
        this.state.nextStep = "scan_location";
    }

    resetScan() {
        this.state.picking_id = null;
        this.state.picking_name = "";
        this.state.picking_origin = "";
        this.state.picking_state = "";
        this.state.destination_id = null;
        this.state.destination_name = "";
        this.state.scanned_packages = [];
        this.state.nextStep = "scan_location";
        this.state.message = "";
        this.showMessage(_t("Scan reset - ready for new transfer"), "info");
        this._focusBarcodeInput();
    }

    exit() {
        this.action.doAction("stock_barcode_lite_homepage");
    }

    _goHome() {
        this.action.doAction("stock_barcode_lite_homepage");
    }

    // ═══════════════════════════════════════════════════════════════
    // 辅助方法
    // ═══════════════════════════════════════════════════════════════

    showMessage(text, type = "info") {
        this.state.message = text;
        this.state.messageType = type;
    }

    _flashScreen(pattern, repeat) {
        if ("vibrate" in navigator) {
            navigator.vibrate(repeat ? pattern : 100);
        }
    }

    formatError(err) {
        return (
            err?.data?.arguments?.[0] ||
            (err?.data?.message
                ? err.data.message.replace(/^odoo\.exceptions\.[^:]+:\s*/, "")
                : "") ||
            err?.message ||
            _t("Unknown error")
        );
    }

    // ═══════════════════════════════════════════════════════════════
    // 计算属性
    // ═══════════════════════════════════════════════════════════════

    get hasPicking() {
        return !!this.state.picking_id;
    }

    get hasDestination() {
        return !!this.state.destination_id;
    }

    get pickingLabel() {
        return this.state.picking_name || "";
    }

    get pickingOrigin() {
        return this.state.picking_origin || "";
    }

    get pickingState() {
        return this.state.picking_state || "";
    }

    get destinationLocationName() {
        return this.state.destination_name || "";
    }

    get isScanLocationStep() {
        return this.state.nextStep === "scan_location";
    }

    get isScanPackageStep() {
        return this.state.nextStep === "scan_package";
    }

    get scanModeLabel() {
        const map = {
            scan_location: _t("Scan Location"),
            scan_package: _t("Scan Pallet"),
        };
        return map[this.state.nextStep] || _t("Scan barcode");
    }

    get stepHint() {
        const hints = {
            scan_location: _t("Scan a destination location barcode"),
            scan_package: _t("Scan pallets to transfer to the destination"),
        };
        return hints[this.state.nextStep] || "";
    }

    get palletList() {
        return Array.isArray(this.state.scanned_packages) ? this.state.scanned_packages : [];
    }

    get isAllComplete() {
        return this.state.scanned_packages.length > 0 &&
               this.state.scanned_packages.every(p => p.is_updated);
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

class InternalTransferPage extends InternalTransfer {}

export { InternalTransfer, InternalTransferPage };
