/** @odoo-module **/

import { onPatched, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { BaseBarcodePage } from "./base_barcode_page";

export class OutboundPalletBinding extends BaseBarcodePage {
    static template = "stock_barcode_lite.OutboundPalletBindingPage";
    static props = { ...standardActionServiceProps };

    setup() {
        super.setup();
        this.quantityInputRef = useRef("quantityInput");
        this.state.outboundOrder = {};
        this.state.currentPallet = {};
        this.state.currentProduct = {};
        this.state.currentTrackingNumber = false;
        this.state.summary = {};
        this.state.pallets = [];
        this.state.expectedProducts = [];
        this.state.lastScan = {};
        this.state.nextStep = "scan_outbound_order";
        this.state.quantityEntry = false;
        this.state.quantityValue = "";
        this.state.productProgressExpanded = false;
        this._refocusBarcodeInputAfterPatch = false;

        onPatched(() => {
            if (this.state.quantityEntry) {
                this.quantityInputRef.el?.focus();
            } else if (this._refocusBarcodeInputAfterPatch) {
                this._refocusBarcodeInputAfterPatch = false;
                this._focusBarcodeInput();
            }
        });
    }

    _onBarcodeBlur() {
        if (!this.state.quantityEntry) {
            super._onBarcodeBlur();
        }
    }

    get stepHint() {
        const hints = {
            scan_outbound_order: _t("Scan the outbound order barcode"),
            scan_package: _t("Scan an existing target pallet whose barcode was generated and printed from the backend"),
            scan_product: _t("Scan a product barcode to add picked items to this pallet"),
            scan_lot: _t("Scan the lot number for the selected product"),
            scan_serial: _t("Scan the serial number for the selected product"),
            input_quantity: _t("Enter the picked quantity"),
        };
        return hints[this.state.nextStep] || _t("Scan a barcode");
    }

    async onBarcodeScanned(barcode) {
        if (!barcode || this.state.loading || this.state.quantityEntry || this._isDestroyed) {
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_outbound_pallet_binding_scan",
                [
                    barcode,
                    this.state.outboundOrder?.id || false,
                    this.state.currentPallet?.id || false,
                    this.state.currentProduct?.id || false,
                    this.state.currentTrackingNumber || false,
                    false,
                ]
            );
            if (!this._isDestroyed) {
                this._applyScanResult(result);
            }
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
                if (!this.state.quantityEntry) {
                    this._focusBarcodeInput();
                }
            }
        }
    }

    _applyScanResult(result) {
        if (!result) {
            return;
        }
        const scanState = result.scan_state || {};
        if (Object.prototype.hasOwnProperty.call(scanState, "outbound_order")) {
            this.state.outboundOrder = scanState.outbound_order || {};
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "current_pallet")) {
            this.state.currentPallet = scanState.current_pallet || {};
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "current_product")) {
            this.state.currentProduct = scanState.current_product || {};
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "current_tracking_number")) {
            this.state.currentTrackingNumber = scanState.current_tracking_number || false;
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "summary")) {
            this.state.summary = scanState.summary || {};
        }
        if (Array.isArray(scanState.pallets)) {
            this.state.pallets = scanState.pallets;
        }
        if (Array.isArray(scanState.expected_products)) {
            this.state.expectedProducts = scanState.expected_products;
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "last_scan")) {
            this.state.lastScan = scanState.last_scan || {};
        }
        this.state.nextStep = result.next_step || this.state.nextStep;

        if (result.message) {
            this.showMessage(result.message, result.success === false ? "danger" : "success");
            if (result.success !== false) {
                this._flashScreen([100, 200, 100], false);
            }
        }
        if (result.success !== false && this.state.nextStep === "input_quantity") {
            this.openQuantityEntry();
        }
    }

    openQuantityEntry() {
        this.state.quantityEntry = true;
        this.state.quantityValue = "";
    }

    _onQuantityKeydown(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            this.submitQuantity();
        }
    }

    cancelQuantityEntry() {
        this.state.quantityEntry = false;
        this.state.quantityValue = "";
        if (this.state.currentProduct?.tracking === "lot") {
            this.state.currentTrackingNumber = false;
            this.state.nextStep = "scan_lot";
        } else {
            this.state.nextStep = "scan_product";
            this.state.currentProduct = {};
        }
        this._refocusBarcodeInputAfterPatch = true;
    }

    async submitQuantity() {
        const quantity = Number(this.state.quantityValue);
        if (!Number.isFinite(quantity) || quantity <= 0) {
            this.showMessage(_t("Enter a quantity greater than zero."), "danger");
            return;
        }
        if (!this.state.outboundOrder?.id || !this.state.currentPallet?.id || !this.state.currentProduct?.id) {
            this.showMessage(_t("Scan an outbound order, target pallet, and product first."), "danger");
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_outbound_pallet_binding_scan",
                [
                    "",
                    this.state.outboundOrder.id,
                    this.state.currentPallet.id,
                    this.state.currentProduct.id,
                    this.state.currentTrackingNumber || false,
                    quantity,
                ]
            );
            if (this._isDestroyed) {
                return;
            }
            this._applyScanResult(result);
            if (result?.success !== false) {
                this.state.quantityEntry = false;
                this.state.quantityValue = "";
                this._refocusBarcodeInputAfterPatch = true;
            }
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
                if (!this.state.quantityEntry && !this._refocusBarcodeInputAfterPatch) {
                    this._focusBarcodeInput();
                }
            }
        }
    }

    switchPallet() {
        this.state.currentPallet = {};
        this.state.currentProduct = {};
        this.state.currentTrackingNumber = false;
        this.state.nextStep = "scan_package";
        this.showMessage(_t("Scan the next target pallet."), "info");
        this._focusBarcodeInput();
    }

    scanAnotherProduct() {
        this.state.currentProduct = {};
        this.state.currentTrackingNumber = false;
        this.state.nextStep = "scan_product";
        this._focusBarcodeInput();
    }

    async removeProduct(pallet, product) {
        if (!this.state.outboundOrder?.id || this.state.loading) {
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_outbound_pallet_binding_remove",
                [this.state.outboundOrder.id, pallet.package_id, product.product_id]
            );
            if (!this._isDestroyed) {
                this._applyScanResult(result);
            }
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
        }
    }

    toggleProductProgress() {
        this.state.productProgressExpanded = !this.state.productProgressExpanded;
    }

    get stepLabel() {
        const labels = {
            scan_outbound_order: _t("Outbound Order"),
            scan_package: _t("Target Pallet"),
            scan_product: _t("Product"),
            scan_lot: _t("Lot"),
            scan_serial: _t("Serial Number"),
            input_quantity: _t("Quantity"),
        };
        return labels[this.state.nextStep] || _t("Ready");
    }

    get hasOutboundOrder() {
        return Boolean(this.state.outboundOrder?.id);
    }

    get hasCurrentPallet() {
        return Boolean(this.state.currentPallet?.id);
    }

    get hasCurrentProduct() {
        return Boolean(this.state.currentProduct?.id);
    }

    get isScanOrderStep() {
        return this.state.nextStep === "scan_outbound_order";
    }

    get isScanPalletStep() {
        return this.state.nextStep === "scan_package";
    }

    get isScanProductStep() {
        return ["scan_product", "scan_lot", "scan_serial", "input_quantity"].includes(this.state.nextStep);
    }

    get palletList() {
        return Array.isArray(this.state.pallets) ? this.state.pallets : [];
    }

    get expectedProductList() {
        return Array.isArray(this.state.expectedProducts) ? this.state.expectedProducts : [];
    }
}
