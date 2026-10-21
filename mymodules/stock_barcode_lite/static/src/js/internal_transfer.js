/** @odoo-module **/

import { BaseBarcodePage } from "./base_barcode_page";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

class InternalTransfer extends BaseBarcodePage {
    static template = "stock_barcode_lite.InternalTransferPage";
    static props = { ...standardActionServiceProps };

    setup() {
        super.setup();

        const data = this.props.action?.params?.picking_data;
        if (data) {
            this._initFromData(data);
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
            this._isProcessing = false;
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
        }
    }

    async _scanLocation(barcode) {
        const result = await this.orm.call("stock.picking", "action_scan_pda_destination_location", [
            [this.state.picking_id], barcode
        ]);
        if (this._isDestroyed) {
            return;
        }
        if (result.success) {
            this.state.destination_id = result.destination_location?.id;
            this.state.destination_name = result.destination_location?.name;
            this.state.scanned_packages = result.package_scan_lines?.map(line => ({
                id: line.id,
                package_id: line.package_id,
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
            [this.state.picking_id], barcode
        ]);
        if (result.success) {
            this.state.scanned_packages = result.package_scan_lines?.map(line => ({
                id: line.id,
                package_id: line.package_id,
                name: line.package_name,
                barcode: line.barcode,
                location_name: line.source_location?.name || "",
                is_updated: true,
            })) || [];
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

        if (data.next_step === "completed") {
            this.state.nextStep = "completed";
        } else if (data.next_step === "scan_package") {
            this.state.nextStep = "scan_package";
        } else {
            // 后端的 scan_destination 对应前端的 scan_location
            this.state.nextStep = "scan_location";
        }

        this.state.destination_id = data.destination_location?.id || null;
        this.state.destination_name = data.destination_location?.name || "";
        this.state.scanned_packages = data.package_scan_lines?.map(line => ({
            id: line.id,
            package_id: line.package_id,
            name: line.package_name,
            barcode: line.barcode,
            location_name: line.source_location?.name || "",
            is_updated: false,
        })) || [];
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

        if (this.state.scanned_packages.length === 0) {
            this.showMessage(_t("Please scan at least one pallet"), "danger");
            return;
        }

        this.state.is_validating = true;
        this.state.loading = true;

        try {
            const result = await this.orm.call("stock.picking", "button_validate", [
                [this.state.picking_id]
            ]);
            if (this._isDestroyed) {
                return;
            }

            if (result?.type) {
                await this.action.doAction(result);
                return;
            }

            // button_validate 成功时返回 True，失败时抛出异常
            this.showMessage(_t("Transfer confirmed successfully!"), "success");
            this._flashScreen([100, 300, 100], true);
            this._safeSetTimeout(() => this._goHome(), 1500);
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            if (!this._isDestroyed) {
                this.state.is_validating = false;
                this.state.loading = false;
            }
        }
    }

    _onRemovePackage(packageId) {
        if (this.state.loading) return;
        this.state.loading = true;
        this.orm.call("stock.picking", "action_remove_pda_package",
            [[this.state.picking_id]],
            { package_id: packageId }
        ).then((result) => {

            if (this._isDestroyed) {
                return;
            }
            if (result && result.success) {
                this.state.scanned_packages = this.state.scanned_packages.filter(p => p.package_id !== packageId);
                this.showMessage(_t("Package removed"), "info");
            }
        }).catch(err => {
            console.error("[InternalTransfer] remove package error:", err);
            this.showMessage(this.formatError(err), "danger");
        }).finally(() => {
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
        });
    }

    resetScan() {
        this.state.loading = true;
        this.orm.call("stock.picking", "action_reset_pda_internal_transfer", [
            [this.state.picking_id]
        ]).then(() => {
            if (!this._isDestroyed) {
                this.state.loading = false;
            }
            this.state.destination_id = null;
            this.state.destination_name = "";
            this.state.scanned_packages = [];
            this.state.nextStep = "scan_location";
            this.state.message = "";
            this.showMessage(_t("Scan reset - ready for new transfer"), "info");
        }).catch(err => {
            console.error("[InternalTransfer] reset error:", err);
        }).finally(() => {
            if (!this._isDestroyed) {
                this.state.loading = false;
            }
        });
    }

    async cancelTransfer() {
        if (!this.state.picking_id) {
            this.exit();
            return;
        }

        this.state.loading = true;
        try {
            await this.orm.call("stock.picking", "action_cancel_pda_internal_transfer", [
                [this.state.picking_id]
            ]);
            this.showMessage(_t("Transfer cancelled"), "info");
            this._flashScreen([200, 100, 100], false);
            this._safeSetTimeout(() => this.exit(), 500);
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
        }
    }

    _goHome() {
        this.action.doAction("stock_barcode_lite_homepage");
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

    get pickingName() {
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
}

class InternalTransferPage extends InternalTransfer {}

export { InternalTransfer, InternalTransferPage };
