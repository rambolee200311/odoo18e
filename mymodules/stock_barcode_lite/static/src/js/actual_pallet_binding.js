/** @odoo-module **/

import { onPatched, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { BaseBarcodePage } from "./base_barcode_page";

export class ActualPalletBinding extends BaseBarcodePage {
    static template = "stock_barcode_lite.ActualPalletBindingPage";
    static props = { ...standardActionServiceProps };

    setup() {
        super.setup();
        this.quantityInputRef = useRef("quantityInput");
        this.state.inbound = {};
        this.state.currentPallet = {};
        this.state.currentProduct = {};
        this.state.summary = {};
        this.state.pallets = [];
        this.state.expandedPalletIds = [];
        this.state.expectedProducts = [];
        this.state.expectedProductsExpanded = false;
        this.state.lastScan = {};
        this.state.nextStep = "scan_inbound";
        this.state.currentTrackingNumber = false;
        this.state.quantityEntry = false;
        this.state.quantityValue = "";
        this.state.editingQuantityId = false;
        this.state.editQuantityValue = "";
        this.state.editingTrackingId = false;
        this.state.editTrackingQuantityValue = "";
        this._trackingHydrationRequest = 0;

        onPatched(() => {
            if (this.state.quantityEntry) {
                this.quantityInputRef.el?.focus();
            }
        });
    }

    _onBarcodeBlur() {
        if (!this.state.quantityEntry) {
            super._onBarcodeBlur();
        }
    }

    get stepHint() {
        if (this.state.quantityEntry) {
            if (this.state.currentTrackingNumber) {
                return _t("Enter the received quantity for lot:") + " " + this.state.currentTrackingNumber;
            }
            return _t("Enter the received quantity for the selected product");
        }
        if (this.state.nextStep === "create_receipt") {
            return _t("Actual pallet binding has been validated.");
        }
        if (!this.state.inbound?.id) {
            return _t("Scan the Inbound order QR code");
        }
        if (!this.state.currentPallet?.id) {
            return _t("Scan a system pallet QR code");
        }
        if (this.state.currentProduct?.id) {
            if (this.state.currentProduct.tracking === "serial") {
                return _t("Scan one or more serial numbers, or scan another product");
            }
            if (this.state.currentProduct.tracking === "lot") {
                return _t("Scan a lot number, or scan another product");
            }
        }
        return _t("Scan a product barcode");
    }

    get expectedQuantity() {
        return this.state.summary?.expected_quantity || 0;
    }

    get actualQuantity() {
        return this.state.summary?.actual_quantity || 0;
    }

    get remainingQuantity() {
        return this.state.summary?.remaining_quantity || 0;
    }

    toggleExpectedProducts() {
        this.state.expectedProductsExpanded = !this.state.expectedProductsExpanded;
    }

    isPalletExpanded(palletId) {
        return this.state.expandedPalletIds.includes(palletId);
    }

    togglePalletExpansion(palletId) {
        this.state.expandedPalletIds = this.isPalletExpanded(palletId)
            ? this.state.expandedPalletIds.filter((id) => id !== palletId)
            : [...this.state.expandedPalletIds, palletId];
    }

    getPalletProductsClass(palletId) {
        return this.isPalletExpanded(palletId)
            ? "o_pallet_products collapse show"
            : "o_pallet_products collapse";
    }

    _isBusy() {
        return this.state.loading || this._isProcessing || this._isDestroyed;
    }

    async onBarcodeScanned(barcode) {
        if (!barcode || this._isBusy() || this.state.quantityEntry) {
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_actual_pallet_binding_scan",
                [
                    barcode,
                    this.state.inbound?.id || false,
                    this.state.currentPallet?.id || false,
                    this.state.currentProduct?.id || false,
                    false,
                    false,
                ]
            );
            if (this._isDestroyed) {
                return;
            }

            this._applyScanResult(result);
            const tracking = this.state.currentProduct?.tracking;
            const selectedQuantityProduct =
                this.state.currentProduct?.id &&
                ["none", "quantity"].includes(tracking) &&
                (result?.next_step === "input_quantity" ||
                    result?.next_step === "enter_quantity" ||
                    result?.next_step === "scan_quantity" ||
                    result?.action?.name === "select_product");
            const selectedLot =
                tracking === "lot" &&
                (result?.type === "lot" || result?.next_step === "input_quantity");
            if (result?.success !== false && (selectedQuantityProduct || selectedLot)) {
                this._openQuantityEntry();
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
            this._isProcessing = false;
        }
    }

    _applyScanResult(result) {
        if (!result) {
            return;
        }

        const scanState = result.scan_state || {};
        if (Object.prototype.hasOwnProperty.call(scanState, "inbound")) {
            this.state.inbound = scanState.inbound || {};
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "current_pallet")) {
            this.state.currentPallet = scanState.current_pallet || {};
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "current_product")) {
            this.state.currentProduct = scanState.current_product || {};
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "summary")) {
            this.state.summary = scanState.summary || {};
        }
        if (Array.isArray(scanState.pallets)) {
            this.state.pallets = scanState.pallets;
            this._hydrateTrackingLineIds();
        }
        if (Array.isArray(scanState.expected_products)) {
            this.state.expectedProducts = scanState.expected_products;
        }
        if (Object.prototype.hasOwnProperty.call(scanState, "last_scan")) {
            this.state.lastScan = scanState.last_scan || {};
        }

        if (result.current) {
            if (Object.prototype.hasOwnProperty.call(result.current, "tracking_number")) {
                this.state.currentTrackingNumber = result.current.tracking_number || false;
            }
            if (Object.prototype.hasOwnProperty.call(result.current, "inbound_order_id") && !result.current.inbound_order_id) {
                this.state.inbound = {};
            }
            if (Object.prototype.hasOwnProperty.call(result.current, "actual_pallet_id") && !result.current.actual_pallet_id) {
                this.state.currentPallet = {};
            }
            if (Object.prototype.hasOwnProperty.call(result.current, "product_id") && !result.current.product_id) {
                this.state.currentProduct = {};
                this.state.currentTrackingNumber = false;
            }
        }

        const availablePalletIds = new Set(this.state.pallets.map((pallet) => pallet.id));
        let expandedPalletIds = this.state.expandedPalletIds.filter((id) => availablePalletIds.has(id));
        if (!this.state.inbound?.id) {
            expandedPalletIds = [];
        } else if (this.state.currentPallet?.id && availablePalletIds.has(this.state.currentPallet.id)) {
            if (!expandedPalletIds.includes(this.state.currentPallet.id)) {
                expandedPalletIds = [...expandedPalletIds, this.state.currentPallet.id];
            }
        }
        this.state.expandedPalletIds = expandedPalletIds;

        this.state.nextStep = result.next_step || this.state.nextStep;

        if (result.message) {
            const messageType = result.success === false ? "danger" : "success";
            this.showMessage(result.message, messageType);
            if (result.success !== false) {
                this._flashScreen([100, 200, 100], false);
            }
        }
    }

    async _hydrateTrackingLineIds() {
        const requestId = ++this._trackingHydrationRequest;
        const productLineIds = [...new Set(
            this.state.pallets.flatMap((pallet) => (pallet.product_lines || []).map((line) => line.id))
        )];
        if (!productLineIds.length) {
            return;
        }
        try {
            const trackingRecords = await this.orm.searchRead(
                "world.depot.inbound.order.actual.pallet.product.serial",
                [["actual_pallet_product_id", "in", productLineIds]],
                ["id", "actual_pallet_product_id", "serial_number", "quantity"]
            );
            if (this._isDestroyed || requestId !== this._trackingHydrationRequest) {
                return;
            }
            const recordsByProductLine = new Map();
            for (const record of trackingRecords) {
                const productLineId = Array.isArray(record.actual_pallet_product_id)
                    ? record.actual_pallet_product_id[0]
                    : record.actual_pallet_product_id;
                const records = recordsByProductLine.get(productLineId) || [];
                records.push(record);
                recordsByProductLine.set(productLineId, records);
            }
            this.state.pallets = this.state.pallets.map((pallet) => ({
                ...pallet,
                product_lines: (pallet.product_lines || []).map((line) => {
                    const records = recordsByProductLine.get(line.id) || [];
                    const unusedRecords = [...records];
                    return {
                        ...line,
                        tracking_lines: (line.tracking_lines || []).map((trackingLine) => {
                            let index = unusedRecords.findIndex((record) =>
                                record.serial_number === trackingLine.number &&
                                Number(record.quantity) === Number(trackingLine.quantity)
                            );
                            if (index < 0) {
                                index = unusedRecords.findIndex((record) => record.serial_number === trackingLine.number);
                            }
                            if (index < 0) {
                                return trackingLine;
                            }
                            const [record] = unusedRecords.splice(index, 1);
                            return { ...trackingLine, id: record.id };
                        }),
                    };
                }),
            }));
            const currentPallet = this.state.pallets.find((pallet) => pallet.id === this.state.currentPallet?.id);
            if (currentPallet) {
                this.state.currentPallet = currentPallet;
            }
        } catch (error) {
            console.warn("Could not load actual pallet tracking record IDs:", error);
        }
    }

    _openQuantityEntry() {
        this.state.quantityEntry = true;
        this.state.quantityValue = "";
    }

    cancelQuantityEntry() {
        this.state.quantityEntry = false;
        this.state.quantityValue = "";
        if (this.state.currentProduct?.tracking === "lot") {
            this.state.currentTrackingNumber = false;
            this.state.nextStep = "scan_lot";
        }
        this._focusBarcodeInput();
    }

    async submitQuantity() {
        const quantity = Number(this.state.quantityValue);
        if (!Number.isFinite(quantity) || quantity <= 0) {
            this.showMessage(_t("Enter a quantity greater than zero."), "danger");
            return;
        }
        const productId = this.state.currentProduct?.id;
        if (!productId || !this.state.inbound?.id || !this.state.currentPallet?.id) {
            this.showMessage(_t("Scan an inbound order, pallet, and product first."), "danger");
            return;
        }
        const trackingNumber = this.state.currentProduct.tracking === "lot"
            ? this.state.currentTrackingNumber
            : false;
        if (this.state.currentProduct.tracking === "lot" && !trackingNumber) {
            this.showMessage(_t("Scan a lot number before entering its quantity."), "danger");
            return;
        }
        if (this._isBusy()) {
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_actual_pallet_binding_scan",
                ["", this.state.inbound.id, this.state.currentPallet.id, productId, trackingNumber, quantity]
            );
            if (this._isDestroyed) {
                return;
            }
            this._applyScanResult(result);
            if (result?.success !== false) {
                this.state.quantityEntry = false;
                this.state.quantityValue = "";
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
            this._isProcessing = false;
        }
    }

    async voidPallet(pallet) {
        if (!pallet?.id || !this.state.inbound?.id || this._isBusy()) {
            return;
        }
        if (!window.confirm(_t("Void this empty actual pallet?"))) {
            return;
        }
        await this._callVoidPallet(pallet.id);
    }

    async validateBinding() {
        if (!this.state.inbound?.id || this._isBusy()) {
            return;
        }
        this._isProcessing = true;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_actual_pallet_binding_validate",
                [this.state.inbound.id]
            );
            if (this._isDestroyed) {
                return;
            }
            this._applyScanResult(result);
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
            this._isProcessing = false;
        }
    }

    async _callVoidPallet(palletId) {
        this._isProcessing = true;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_actual_pallet_binding_void",
                [this.state.inbound.id, palletId]
            );
            if (this._isDestroyed) {
                return;
            }
            this._applyScanResult(result);
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
            }
        } finally {
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
            this._isProcessing = false;
        }
    }

    beginQuantityEdit(line) {
        this.state.editingQuantityId = line.id;
        this.state.editQuantityValue = String(line.quantity ?? "");
    }

    cancelQuantityEdit() {
        this.state.editingQuantityId = false;
        this.state.editQuantityValue = "";
    }

    async saveQuantityEdit(pallet, line) {
        const quantity = Number(this.state.editQuantityValue);
        if (!Number.isFinite(quantity) || quantity <= 0) {
            this.showMessage(_t("Enter a quantity greater than zero."), "danger");
            return;
        }
        await this._callEdit(
            "update_quantity",
            pallet.id,
            line.id,
            false,
            quantity,
            () => this.cancelQuantityEdit(),
            () => this._updateProductQuantityLocally(pallet.id, line, quantity)
        );
    }

    beginTrackingQuantityEdit(line, trackingLine) {
        this.state.editingTrackingId = trackingLine.id;
        this.state.editTrackingQuantityValue = String(trackingLine.quantity ?? "");
    }

    cancelTrackingQuantityEdit() {
        this.state.editingTrackingId = false;
        this.state.editTrackingQuantityValue = "";
    }

    async saveTrackingQuantityEdit(pallet, line, trackingLine) {
        const quantity = Number(this.state.editTrackingQuantityValue);
        if (!Number.isFinite(quantity) || quantity <= 0) {
            this.showMessage(_t("Enter a quantity greater than zero."), "danger");
            return;
        }
        await this._callEdit(
            "update_quantity",
            pallet.id,
            line.id,
            trackingLine.id,
            quantity,
            () => this.cancelTrackingQuantityEdit(),
            () => this._updateTrackingLocally(pallet.id, line, trackingLine, quantity)
        );
    }

    async deleteProduct(pallet, line) {
        if (!line?.id || this._isBusy()) {
            return;
        }
        if (!window.confirm(_t("Delete this product and all of its serial or lot entries?"))) {
            return;
        }
        await this._callEdit("delete_product", pallet.id, line.id, false, false, false, () => {
            this._removeProductLocally(pallet.id, line);
        });
    }

    async deleteTracking(pallet, line, trackingLine) {
        if (!line?.id || !trackingLine?.id || this._isBusy()) {
            return;
        }
        const trackingLabel = trackingLine.number || trackingLine.name || "";
        if (!window.confirm(_t("Delete tracking number: ") + trackingLabel + "?")) {
            return;
        }
        await this._callEdit("delete_tracking", pallet.id, line.id, trackingLine.id, false, false, () => {
            this._removeTrackingLocally(pallet.id, line, trackingLine);
        });
    }

    async _callEdit(operation, actualPalletId, productLineId, trackingLineId, quantity, afterSuccess, applyLocal) {
        if (!this.state.inbound?.id || !actualPalletId || this._isBusy()) {
            this.showMessage(_t("Scan an inbound order and pallet first."), "danger");
            return;
        }
        this._isProcessing = true;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_actual_pallet_binding_edit",
                [operation, this.state.inbound.id, actualPalletId, productLineId, trackingLineId || false, quantity || false]
            );
            if (this._isDestroyed) {
                return;
            }
            this._applyScanResult(result);
            if (result?.success !== false) {
                if (Object.keys(result?.scan_state || {}).length === 0 && applyLocal) {
                    applyLocal();
                }
                afterSuccess?.();
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
            this._isProcessing = false;
        }
    }

    _removeProductLocally(actualPalletId, line) {
        const quantity = Number(line.quantity) || 0;
        const pallet = this.state.pallets.find((item) => item.id === actualPalletId);
        const remainingLines = (pallet?.product_lines || []).filter((item) => item.id !== line.id);
        this._setPalletLines(actualPalletId, remainingLines);
        this._adjustProductTotals(line.product_id, -quantity);
    }

    _removeTrackingLocally(actualPalletId, line, trackingLine) {
        const pallet = this.state.pallets.find((item) => item.id === actualPalletId);
        const trackingLines = (line.tracking_lines || []).filter((item) => item.id !== trackingLine.id);
        const removedQuantity = Number(trackingLine.quantity) || 1;
        const remainingQuantity = Math.max(0, (Number(line.quantity) || 0) - removedQuantity);
        let remainingLines = (pallet?.product_lines || []).map((item) =>
            item.id === line.id
                ? { ...item, quantity: remainingQuantity, tracking_lines: trackingLines }
                : item
        );
        if (remainingQuantity <= 0) {
            remainingLines = remainingLines.filter((item) => item.id !== line.id);
        }
        this._setPalletLines(actualPalletId, remainingLines);
        this._adjustProductTotals(line.product_id, -removedQuantity);
    }

    _updateTrackingLocally(actualPalletId, line, trackingLine, quantity) {
        const pallet = this.state.pallets.find((item) => item.id === actualPalletId);
        const updatedLines = (pallet?.product_lines || []).map((item) => {
            if (item.id !== line.id) {
                return item;
            }
            const trackingLines = (item.tracking_lines || []).map((trackingItem) =>
                trackingItem.id === trackingLine.id
                    ? { ...trackingItem, quantity }
                    : trackingItem
            );
            return {
                ...item,
                quantity: (Number(item.quantity) || 0) + quantity - (Number(trackingLine.quantity) || 0),
                tracking_lines: trackingLines,
            };
        });
        this._setPalletLines(actualPalletId, updatedLines);
        this._adjustProductTotals(line.product_id, quantity - (Number(trackingLine.quantity) || 0));
    }

    _updateProductQuantityLocally(actualPalletId, line, quantity) {
        const pallet = this.state.pallets.find((item) => item.id === actualPalletId);
        const updatedLines = (pallet?.product_lines || []).map((item) =>
            item.id === line.id ? { ...item, quantity } : item
        );
        this._setPalletLines(actualPalletId, updatedLines);
        this._adjustProductTotals(line.product_id, quantity - (Number(line.quantity) || 0));
    }

    _setPalletLines(actualPalletId, lines) {
        this._trackingHydrationRequest++;
        this.state.pallets = this.state.pallets.map((pallet) =>
            pallet.id === actualPalletId
                ? { ...pallet, product_lines: lines }
                : pallet
        );
        if (this.state.currentPallet.id === actualPalletId) {
            this.state.currentPallet = { ...this.state.currentPallet, product_lines: lines };
        }
    }

    _adjustProductTotals(productId, delta) {
        this.state.expectedProducts = this.state.expectedProducts.map((product) => {
            if (product.product_id !== productId) {
                return product;
            }
            const actual = Math.max(0, (Number(product.actual_quantity) || 0) + delta);
            return {
                ...product,
                actual_quantity: actual,
                remaining_quantity: Math.max(0, (Number(product.expected_quantity) || 0) - actual),
            };
        });
        const actual = Math.max(0, (Number(this.state.summary.actual_quantity) || 0) + delta);
        this.state.summary = {
            ...this.state.summary,
            actual_quantity: actual,
            remaining_quantity: Math.max(0, (Number(this.state.summary.expected_quantity) || 0) - actual),
        };
    }
}
