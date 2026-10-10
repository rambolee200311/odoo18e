/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class BlindStockCountScan extends Component {
    static template = "blind_stock_count.ScanPage";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.barcodeInputRef = useRef("barcodeInput");
        this.processing = false;
        const action = this.env.config.action || {};
        this.continueCountId = this.props?.action?.params?.blind_stock_count_id || action.params?.blind_stock_count_id || action.context?.blind_stock_count_id || false;
        this.newWorkPackageId = this.props?.action?.params?.work_package_id || action.params?.work_package_id || action.context?.work_package_id || false;
        this.onPageInteraction = () => {
            if (!this.processing && this.state.count?.state !== "done" && !["select_work_package", "input_quantity", "input_lot_quantity"].includes(this.state.nextStep)) {
                this.focusBarcodeInput();
            }
        };
        this.state = useState({
            loading: false,
            message: "",
            messageType: "info",
            workPackages: [],
            workPackageId: false,
            workPackageName: "",
            count: null,
            locationVerified: false,
            pallet: null,
            pallets: [],
            expandedPalletId: false,
            product: null,
            editingLineId: false,
            lastScannedLineIds: [],
            lotName: "",
            quantity: "",
            nextStep: "select_work_package",
        });
        onMounted(async () => {
            document.addEventListener("click", this.onPageInteraction);
            document.addEventListener("touchstart", this.onPageInteraction, { passive: true });
            if (this.continueCountId) {
                const result = await this.call("get_continue_scan_data", [this.continueCountId]);
                if (result) {
                    this.state.workPackageId = result.work_package.id;
                    this.state.workPackageName = result.work_package.name;
                    this.state.count = result.count;
                    const pallets = result.pallets || [];
                    this.state.pallets = pallets;
                    this.state.pallet = null;
                    this.state.expandedPalletId = false;
                    this.state.locationVerified = result.count.state === "done";
                    this.state.nextStep = result.count.state === "done" ? "done" : "scan_location";
                    this.showMessage(result.count.state === "done" ? _t("Completed blind stock count loaded. View only.") : _t("Blind stock count loaded. Scan the count location to verify it before continuing."));
                }
            } else {
                await this.loadWorkPackages();
                const workPackage = this.state.workPackages.find((item) => item.id === Number(this.newWorkPackageId));
                if (workPackage) {
                    this.state.workPackageId = workPackage.id;
                    this.state.workPackageName = workPackage.name;
                    this.state.nextStep = "scan_location";
                    this.showMessage(_t("Work package selected. Now scan the internal location."));
                }
            }
            this.focusBarcodeInput();
        });
        onPatched(() => this.onPageInteraction());
        onWillUnmount(() => {
            document.removeEventListener("click", this.onPageInteraction);
            document.removeEventListener("touchstart", this.onPageInteraction);
        });
    }

    async loadWorkPackages() {
        const workPackages = await this.call("get_scannable_work_packages", []);
        if (workPackages) {
            this.state.workPackages = workPackages;
        }
    }

    async call(method, args, scannedBarcode = "") {
        this.processing = true;
        this.state.loading = true;
        try {
            return await this.orm.call("blind.stock.count", method, args);
        } catch (error) {
            const message = error?.data?.message || error?.message || _t("Operation failed.");
            this.showMessage(scannedBarcode ? `${_t("Scanned barcode:")} ${scannedBarcode}. ${message}` : message, "danger");
            return null;
        } finally {
            this.processing = false;
            this.state.loading = false;
            this.focusBarcodeInput();
        }
    }

    focusBarcodeInput() {
        if (this.state.count?.state === "done") {
            return;
        }
        setTimeout(() => this.barcodeInputRef.el?.focus(), 0);
    }

    showMessage(message, messageType = "info") {
        this.state.message = message;
        this.state.messageType = messageType;
    }

    setPallet(pallet, moveToTop = false) {
        this.state.pallet = pallet;
        const isNewPallet = !this.state.pallets.some((item) => item.id === pallet.id);
        this.state.pallets = moveToTop || isNewPallet ? [pallet, ...this.state.pallets.filter((item) => item.id !== pallet.id)] : this.state.pallets.map((item) => item.id === pallet.id ? pallet : item);
    }

    selectScannedProduct(product) {
        const hasManualLine = product.tracking === "none" && product.manual_line_id;
        this.state.product = product;
        if (hasManualLine) {
            const productLines = this.state.pallet.product_lines || [];
            this.setPallet({ ...this.state.pallet, product_lines: [...productLines.filter((line) => line.id === product.manual_line_id), ...productLines.filter((line) => line.id !== product.manual_line_id)] });
        }
        this.state.editingLineId = hasManualLine || false;
        this.state.lotName = "";
        this.state.quantity = product.tracking === "none" ? product.counted_qty || "" : "";
        this.state.lastScannedLineIds = [];
        this.state.nextStep = product.tracking === "none" ? "input_quantity" : product.tracking === "lot" ? "scan_lot_name" : "scan_serial_numbers";
        return hasManualLine ? _t("Edit the counted quantity.") : product.tracking === "none" ? _t("Enter the counted quantity.") : product.tracking === "lot" ? _t("Now scan a batch number.") : _t("Now scan serial number(s).")
    }

    selectPallet(pallet) {
        if (this.state.count?.state === "done") {
            this.state.expandedPalletId = this.state.expandedPalletId === pallet.id ? false : pallet.id;
            return;
        }
        if (!this.state.locationVerified) {
            this.showMessage(_t("Scan and verify the count location before selecting a pallet."), "warning");
            return;
        }
        if (["input_quantity", "input_lot_quantity"].includes(this.state.nextStep)) {
            this.showMessage(_t("Record or cancel the quantity before changing pallets."), "warning");
            return;
        }
        if (this.state.expandedPalletId === pallet.id) {
            this.state.pallet = null;
            this.state.expandedPalletId = false;
            this.state.product = null;
            this.state.editingLineId = false;
            this.state.lastScannedLineIds = [];
            this.state.lotName = "";
            this.state.quantity = "";
            this.state.nextStep = "scan_pallet";
            this.showMessage(_t("Pallet collapsed. Tap a pallet to continue or scan a new pallet."));
            this.focusBarcodeInput();
            return;
        }
        this.setPallet(pallet);
        this.state.expandedPalletId = pallet.id;
        this.state.product = null;
        this.state.editingLineId = false;
        this.state.lastScannedLineIds = [];
        this.state.lotName = "";
        this.state.quantity = "";
        this.state.nextStep = "scan_product";
        this.showMessage(_t("Pallet selected. Now scan a product."));
        this.focusBarcodeInput();
    }

    onWorkPackageChange(event) {
        this.state.workPackageId = Number(event.target.value) || false;
        this.state.workPackageName = event.target.selectedOptions[0]?.dataset.name || "";
    }

    confirmWorkPackage() {
        if (!this.state.workPackageId) {
            this.showMessage(_t("Please select a work package."), "danger");
            return;
        }
        this.state.nextStep = "scan_location";
        this.showMessage(_t("Now scan the internal location."));
        this.focusBarcodeInput();
    }

    onBarcodeKeydown(event) {
        if (event.key !== "Enter") {
            return;
        }
        event.preventDefault();
        const barcode = event.target.value.trim();
        event.target.value = "";
        if (barcode) {
            this.onBarcodeScanned(barcode);
        }
    }

    onBarcodeInput(event) {
        if (event.inputType !== "insertLineFeed" && !event.target.value.includes("\n") && !event.target.value.includes("\r")) {
            return;
        }
        const barcode = event.target.value.replace(/\n/g, "").replace(/\r/g, "").trim();
        event.target.value = "";
        if (barcode) {
            this.onBarcodeScanned(barcode);
        }
    }

    onBarcodeBlur() {
        this.onPageInteraction();
    }

    async onBarcodeScanned(barcode) {
        if (this.processing || this.state.count?.state === "done" || this.state.nextStep === "select_work_package") {
            return;
        }
        if (["input_quantity", "input_lot_quantity"].includes(this.state.nextStep)) {
            this.showMessage(_t("Record or cancel the quantity before scanning the next product."), "warning");
            return;
        }
        if (this.state.nextStep === "scan_location") {
            const result = await this.call(this.state.count ? "action_verify_count_location" : "action_scan_location", this.state.count ? [this.state.count.id, barcode] : [this.state.workPackageId, barcode], barcode);
            if (result) {
                this.state.count = result.count;
                this.state.locationVerified = true;
                this.state.nextStep = "scan_pallet";
                this.showMessage(result.message, "success");
                this.focusBarcodeInput();
            }
            return;
        }
        if (this.state.nextStep === "scan_pallet") {
            const result = await this.call("action_scan_package", [this.state.count.id, barcode], barcode);
            if (result) {
                this.setPallet(result.pallet, !this.state.pallets.some((item) => item.id === result.pallet.id));
                this.state.expandedPalletId = result.pallet.id;
                this.state.product = null;
                this.state.editingLineId = false;
                this.state.lastScannedLineIds = [];
                this.state.lotName = "";
                this.state.nextStep = "scan_product";
                this.showMessage(result.message, "success");
                this.focusBarcodeInput();
            }
            return;
        }
        if (["scan_product", "scan_lot_name", "scan_serial_numbers"].includes(this.state.nextStep)) {
            const scanResult = await this.call("classify_scan_value", [this.state.pallet.id, barcode], barcode);
            if (!scanResult) {
                return;
            }
            if (scanResult.scan_type === "pallet") {
                this.setPallet(scanResult.pallet, !this.state.pallets.some((item) => item.id === scanResult.pallet.id));
                this.state.expandedPalletId = scanResult.pallet.id;
                this.state.product = null;
                this.state.editingLineId = false;
                this.state.lastScannedLineIds = [];
                this.state.lotName = "";
                this.state.nextStep = "scan_product";
                this.showMessage(_t("Pallet scanned. Now scan a product."), "success");
                return;
            }
            if (scanResult.scan_type === "product") {
                this.showMessage(this.selectScannedProduct(scanResult.product), "success");
                return;
            }
            if (scanResult.scan_type === "out_of_scope") {
                this.showMessage(_t("Product %s does not belong to the current work package product category.", scanResult.product_name), "danger");
                return;
            }
            if (this.state.nextStep === "scan_product") {
                this.showMessage(_t("No product matches this barcode."), "danger");
                return;
            }
        }
        if (this.state.nextStep === "scan_lot_name") {
            this.state.lotName = barcode;
            this.state.quantity = "";
            this.state.nextStep = "input_lot_quantity";
            this.showMessage(_t("Batch number scanned. Enter the counted quantity."), "success");
            return;
        }
        if (this.state.nextStep === "scan_serial_numbers") {
            const result = await this.call("action_scan_serial_numbers", [this.state.pallet.id, this.state.product.id, barcode], barcode);
            if (result) {
                this.setPallet(result.pallet);
                this.state.expandedPalletId = result.pallet.id;
                this.state.product.scanned_serial_count = result.scanned_serial_count;
                this.state.lastScannedLineIds = result.line_ids || [];
                this.showMessage(result.message, "success");
                this.focusBarcodeInput();
            }
        }
    }

    editManualQuantity(pallet, line, event) {
        if (this.state.count?.state === "done" || line.tracking !== "none") {
            return;
        }
        event.stopPropagation();
        this.setPallet(pallet);
        this.state.expandedPalletId = pallet.id;
        this.state.product = { id: line.product_id, name: line.name, barcode: line.barcode, tracking: line.tracking };
        this.state.editingLineId = line.id;
        this.state.lastScannedLineIds = [];
        this.state.quantity = line.counted_qty;
        this.state.nextStep = "input_quantity";
        this.showMessage(_t("Edit the counted quantity."));
        this.focusBarcodeInput();
    }

    async deleteLine(pallet, line, event) {
        event.stopPropagation();
        if (this.state.count?.state === "done") {
            return;
        }
        const result = await this.call("action_delete_line", [line.id]);
        if (result) {
            const isCurrentPallet = this.state.pallet && this.state.pallet.id === pallet.id;
            this.state.pallets = this.state.pallets.map((item) => item.id === result.pallet.id ? result.pallet : item);
            if (isCurrentPallet) {
                this.state.pallet = result.pallet;
                this.state.expandedPalletId = result.pallet.id;
            }
            this.state.lastScannedLineIds = [];
            if (isCurrentPallet && this.state.product?.id === result.product_id && this.state.product.tracking === "none") {
                this.state.product = null;
                this.state.editingLineId = false;
                this.state.quantity = "";
                this.state.nextStep = "scan_product";
            } else if (isCurrentPallet && this.state.product?.id === result.product_id) {
                this.state.product.scanned_serial_count = result.scanned_serial_count;
            }
            this.showMessage(result.message, "success");
            this.focusBarcodeInput();
        }
    }

    async addManualQuantity() {
        if (!this.state.quantity) {
            this.showMessage(_t("Enter the counted quantity."), "danger");
            return;
        }
        const result = await this.call("action_add_manual_quantity", [this.state.pallet.id, this.state.product.id, this.state.quantity]);
        if (result) {
            this.setPallet(result.pallet);
            this.state.expandedPalletId = result.pallet.id;
            this.state.lastScannedLineIds = result.line_ids || [];
            this.state.quantity = "";
            this.state.product = null;
            this.state.editingLineId = false;
            this.state.nextStep = "scan_product";
            this.showMessage(result.message, "success");
            this.focusBarcodeInput();
        }
    }

    async addLotQuantity() {
        if (!this.state.lotName) {
            this.showMessage(_t("Scan a batch number."), "danger");
            return;
        }
        if (!this.state.quantity) {
            this.showMessage(_t("Enter the counted quantity."), "danger");
            return;
        }
        const result = await this.call("action_add_lot_quantity", [this.state.pallet.id, this.state.product.id, this.state.lotName, this.state.quantity]);
        if (result) {
            this.setPallet(result.pallet);
            this.state.expandedPalletId = result.pallet.id;
            this.state.lastScannedLineIds = result.line_ids || [];
            this.state.lotName = "";
            this.state.quantity = "";
            this.state.product = null;
            this.state.editingLineId = false;
            this.state.nextStep = "scan_product";
            this.showMessage(result.message, "success");
            this.focusBarcodeInput();
        }
    }

    switchProduct() {
        this.state.product = null;
        this.state.editingLineId = false;
        this.state.lastScannedLineIds = [];
        this.state.lotName = "";
        this.state.quantity = "";
        this.state.nextStep = "scan_product";
        this.showMessage(_t("Now scan a product."));
        this.focusBarcodeInput();
    }

    switchPallet() {
        this.state.pallet = null;
        this.state.expandedPalletId = false;
        this.state.product = null;
        this.state.editingLineId = false;
        this.state.lastScannedLineIds = [];
        this.state.lotName = "";
        this.state.quantity = "";
        this.state.nextStep = "scan_pallet";
        this.showMessage(_t("Now scan a pallet."));
        this.focusBarcodeInput();
    }

    async completeCount() {
        if (!this.state.count || this.state.count.state === "done") {
            return;
        }
        const result = await this.call("action_done", [[this.state.count.id]]);
        if (result) {
            this.state.count = null;
            this.state.locationVerified = false;
            this.state.pallet = null;
            this.state.pallets = [];
            this.state.expandedPalletId = false;
            this.state.product = null;
            this.state.editingLineId = false;
            this.state.lastScannedLineIds = [];
            this.state.lotName = "";
            this.state.quantity = "";
            this.state.nextStep = "scan_location";
            this.showMessage(_t("Blind stock count completed. Scan the next internal location."), "success");
            this.focusBarcodeInput();
        }
    }

    async returnToCounting() {
        if (!this.state.count?.can_return_to_counting) {
            return;
        }
        const result = await this.call("action_return_to_counting", [[this.state.count.id]]);
        const scanData = result && await this.call("get_continue_scan_data", [this.state.count.id]);
        if (scanData) {
            this.state.count = scanData.count;
            this.state.pallets = scanData.pallets || [];
            this.state.locationVerified = false;
            this.state.pallet = null;
            this.state.expandedPalletId = false;
            this.state.product = null;
            this.state.editingLineId = false;
            this.state.lastScannedLineIds = [];
            this.state.lotName = "";
            this.state.quantity = "";
            this.state.nextStep = "scan_location";
            this.showMessage(_t("Blind stock count returned to counting. Scan the count location to continue."), "success");
            this.focusBarcodeInput();
        }
    }
}

registry.category("actions").add("blind_stock_count.scan", BlindStockCountScan);

export class BlindStockCountCheckScan extends Component {
    static template = "blind_stock_count.CheckScanPage";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.barcodeInputRef = useRef("checkBarcodeInput");
        this.processing = false;
        const action = this.env.config.action || {};
        this.checkId = this.props?.action?.params?.blind_stock_count_check_id || action.params?.blind_stock_count_check_id || false;
        this.onPageInteraction = (event) => {
            const target = event?.target;
            const activeElement = document.activeElement;
            const isEditingField = target?.closest("input:not(.o_hidden_barcode_input), textarea, select") || activeElement?.matches("input:not(.o_hidden_barcode_input), textarea, select");
            if (!this.processing && this.state.check?.state !== "done" && !isEditingField && !["input_quantity", "input_lot_quantity"].includes(this.state.nextStep)) {
                this.focusBarcodeInput();
            }
        };
        this.state = useState({ loading: false, message: "", messageType: "info", check: null, locationVerified: false, pallet: null, pallets: [], expandedPalletId: false, product: null, lotName: "", quantity: "", lastScannedLineIds: [], conclusion: "pending", conclusionNote: "", nextStep: "scan_location" });
        onMounted(async () => {
            document.addEventListener("click", this.onPageInteraction);
            document.addEventListener("touchstart", this.onPageInteraction, { passive: true });
            const result = await this.call("get_check_scan_data", [this.checkId]);
            if (result) {
                this.state.check = result.check;
                this.state.pallets = result.pallets || [];
                this.state.conclusion = result.check.conclusion || "pending";
                this.state.conclusionNote = result.check.conclusion_note || "";
                this.showMessage(result.check.state === "done" ? _t("Completed check loaded. View only.") : _t("Check loaded. Scan the count location to verify it before continuing."));
            }
            this.focusBarcodeInput();
        });
        onPatched(() => this.onPageInteraction());
        onWillUnmount(() => {
            document.removeEventListener("click", this.onPageInteraction);
            document.removeEventListener("touchstart", this.onPageInteraction);
        });
    }

    async call(method, args, scannedBarcode = "") {
        this.processing = true;
        this.state.loading = true;
        try {
            return await this.orm.call("blind.stock.count.check", method, args);
        } catch (error) {
            const message = error?.data?.message || error?.message || _t("Operation failed.");
            this.showMessage(scannedBarcode ? `${_t("Scanned barcode:")} ${scannedBarcode}. ${message}` : message, "danger");
            return null;
        } finally {
            this.processing = false;
            this.state.loading = false;
            this.focusBarcodeInput();
        }
    }

    focusBarcodeInput() {
        if (this.state.check?.state === "done") {
            return;
        }
        setTimeout(() => {
            if (!document.activeElement?.matches("input:not(.o_hidden_barcode_input), textarea, select")) {
                this.barcodeInputRef.el?.focus();
            }
        }, 0);
    }

    showMessage(message, messageType = "info") {
        this.state.message = message;
        this.state.messageType = messageType;
    }

    setPallet(pallet) {
        this.state.pallet = pallet;
        const isNewPallet = !this.state.pallets.some((item) => item.id === pallet.id);
        this.state.pallets = isNewPallet ? [pallet, ...this.state.pallets] : this.state.pallets.map((item) => item.id === pallet.id ? pallet : item);
    }

    selectPallet(pallet) {
        if (this.state.check?.state === "done") {
            this.state.expandedPalletId = this.state.expandedPalletId === pallet.id ? false : pallet.id;
            return;
        }
        if (!this.state.locationVerified) {
            this.showMessage(_t("Scan and verify the count location before selecting a pallet."), "warning");
            return;
        }
        if (["input_quantity", "input_lot_quantity"].includes(this.state.nextStep)) {
            this.showMessage(_t("Record or cancel the quantity before changing pallets."), "warning");
            return;
        }
        if (this.state.expandedPalletId === pallet.id) {
            this.state.pallet = null;
            this.state.expandedPalletId = false;
            this.state.product = null;
            this.state.lotName = "";
            this.state.quantity = "";
            this.state.lastScannedLineIds = [];
            this.state.nextStep = "scan_pallet";
            this.showMessage(_t("Pallet collapsed. Scan a pallet to continue."));
            return;
        }
        this.setPallet(pallet);
        this.state.expandedPalletId = pallet.id;
        this.state.product = null;
        this.state.lotName = "";
        this.state.quantity = "";
        this.state.lastScannedLineIds = [];
        this.state.nextStep = "scan_product";
        this.showMessage(_t("Pallet selected. Now scan a product."));
    }

    onBarcodeKeydown(event) {
        if (event.key !== "Enter") {
            return;
        }
        event.preventDefault();
        const barcode = event.target.value.trim();
        event.target.value = "";
        if (barcode) {
            this.onBarcodeScanned(barcode);
        }
    }

    onBarcodeInput(event) {
        if (event.inputType !== "insertLineFeed" && !event.target.value.includes("\n") && !event.target.value.includes("\r")) {
            return;
        }
        const barcode = event.target.value.replace(/\n/g, "").replace(/\r/g, "").trim();
        event.target.value = "";
        if (barcode) {
            this.onBarcodeScanned(barcode);
        }
    }

    onBarcodeBlur() {
        this.onPageInteraction();
    }

    async onBarcodeScanned(barcode) {
        if (this.processing || !this.state.check || this.state.check.state === "done") {
            return;
        }
        if (["input_quantity", "input_lot_quantity"].includes(this.state.nextStep)) {
            this.showMessage(_t("Record or cancel the quantity before scanning the next item."), "warning");
            return;
        }
        if (this.state.nextStep === "scan_location") {
            const result = await this.call("action_scan_location", [this.state.check.id, barcode], barcode);
            if (result) {
                this.state.locationVerified = true;
                this.state.nextStep = "scan_pallet";
                this.showMessage(result.message, "success");
            }
            return;
        }
        if (this.state.nextStep === "scan_pallet") {
            const result = await this.call("action_scan_package", [this.state.check.id, barcode], barcode);
            if (result) {
                this.setPallet(result.pallet);
                this.state.expandedPalletId = result.pallet.id;
                this.state.product = null;
                this.state.lotName = "";
                this.state.quantity = "";
                this.state.lastScannedLineIds = [];
                this.state.nextStep = "scan_product";
                this.showMessage(result.message, result.message_type || "success");
            }
            return;
        }
        if (["scan_product", "scan_lot_name", "scan_serial_numbers"].includes(this.state.nextStep)) {
            const result = await this.call("get_scanned_pallet", [this.state.check.id, barcode], barcode);
            if (result) {
                this.setPallet(result.pallet);
                this.state.expandedPalletId = result.pallet.id;
                this.state.product = null;
                this.state.lotName = "";
                this.state.quantity = "";
                this.state.lastScannedLineIds = [];
                this.state.nextStep = "scan_product";
                this.showMessage(result.message, "success");
                return;
            }
        }
        if (this.state.nextStep === "scan_product") {
            const result = await this.call("action_scan_product", [this.state.check.id, this.state.pallet.source_pallet_id || false, this.state.pallet.barcode || this.state.pallet.name, barcode], barcode);
            if (result) {
                if (result.recorded_anomaly) {
                    this.setPallet(result.pallet);
                    this.state.expandedPalletId = result.pallet.id;
                    this.state.product = null;
                    this.state.lastScannedLineIds = [];
                    this.state.nextStep = "scan_product";
                    this.showMessage(result.message, result.message_type || "warning");
                    return;
                }
                this.state.product = result.product;
                this.state.lotName = "";
                this.state.quantity = result.product.tracking === "none" ? result.product.checked_qty || "" : "";
                this.state.lastScannedLineIds = [];
                this.state.nextStep = result.product.tracking === "none" ? "input_quantity" : result.product.tracking === "lot" ? "scan_lot_name" : "scan_serial_numbers";
                this.showMessage(result.message || (result.product.tracking === "none" ? _t("Enter the sampled quantity.") : result.product.tracking === "lot" ? _t("Now scan a batch number.") : _t("Now scan serial number(s).")), result.message_type || "success");
            }
            return;
        }
        if (this.state.nextStep === "scan_lot_name") {
            this.state.lotName = barcode;
            this.state.quantity = "";
            this.state.nextStep = "input_lot_quantity";
            this.showMessage(_t("Batch number scanned. Enter the sampled quantity."), "success");
            return;
        }
        if (this.state.nextStep === "scan_serial_numbers") {
            const result = await this.call("action_scan_serial_numbers", [this.state.check.id, this.state.pallet.source_pallet_id || false, this.state.pallet.barcode || this.state.pallet.name, this.state.product.id, barcode, this.state.product.anomaly_status || false], barcode);
            if (result) {
                this.setPallet(result.pallet);
                this.state.expandedPalletId = result.pallet.id;
                this.state.product.checked_serial_count = result.checked_serial_count;
                this.state.lastScannedLineIds = result.line_ids || [];
                this.showMessage(result.message, result.message_type || "success");
            }
        }
    }

    async addQuantity() {
        if (!this.state.quantity) {
            this.showMessage(_t("Enter the sampled quantity."), "danger");
            return;
        }
        if (this.state.product.tracking === "lot" && !this.state.lotName) {
            this.showMessage(_t("Scan a batch number."), "danger");
            return;
        }
        const result = await this.call("action_add_quantity", [this.state.check.id, this.state.pallet.source_pallet_id || false, this.state.pallet.barcode || this.state.pallet.name, this.state.product.id, this.state.product.tracking === "lot" ? this.state.lotName : "", this.state.quantity, this.state.product.anomaly_status || false]);
        if (result) {
            this.setPallet(result.pallet);
            this.state.expandedPalletId = result.pallet.id;
            this.state.lastScannedLineIds = result.line_ids || [];
            this.state.product = null;
            this.state.lotName = "";
            this.state.quantity = "";
            this.state.nextStep = "scan_product";
            this.showMessage(result.match_status === "matched" ? _t("Sample recorded and matched.") : _t("Sample anomaly recorded."), result.match_status === "matched" ? "success" : "warning");
        }
    }

    switchProduct() {
        this.state.product = null;
        this.state.lotName = "";
        this.state.quantity = "";
        this.state.lastScannedLineIds = [];
        this.state.nextStep = this.state.pallet ? "scan_product" : "scan_pallet";
        this.showMessage(this.state.pallet ? _t("Now scan a product.") : _t("Now scan a pallet."));
    }

    switchPallet() {
        this.state.pallet = null;
        this.state.expandedPalletId = false;
        this.state.product = null;
        this.state.lotName = "";
        this.state.quantity = "";
        this.state.lastScannedLineIds = [];
        this.state.nextStep = "scan_pallet";
        this.showMessage(_t("Now scan a pallet."));
    }

    async completeCheck() {
        if (!this.state.check || this.state.check.state === "done") {
            return;
        }
        if (this.state.conclusion === "pending") {
            this.showMessage(_t("Pending cannot be completed. Select Passed, Failed, or Uncertain."), "danger");
            return;
        }
        const result = await this.call("action_done", [[this.state.check.id], this.state.conclusion, this.state.conclusionNote]);
        if (result) {
            this.action.doAction("blind_stock_count.action_blind_stock_count_check_pda_list");
        }
    }
}

registry.category("actions").add("blind_stock_count.check_scan", BlindStockCountCheckScan);

export class BlindStockCountCheckPdaList extends Component {
    static template = "blind_stock_count.CheckPdaList";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, checks: [], message: "" });
        onMounted(() => this.loadChecks());
    }

    async loadChecks() {
        this.state.loading = true;
        try {
            this.state.checks = await this.orm.call("blind.stock.count.check", "get_pda_check_list", []);
        } catch (error) {
            this.state.message = error?.data?.message || error?.message || _t("Unable to load blind stock count checks.");
        } finally {
            this.state.loading = false;
        }
    }

    async openCheck(check) {
        this.state.loading = true;
        try {
            if (check.state === "draft") {
                await this.orm.call("blind.stock.count.check", "action_start_checking", [[check.id]]);
            }
            this.action.doAction({ type: "ir.actions.client", tag: "blind_stock_count.check_scan", target: "main", params: { blind_stock_count_check_id: check.id } });
        } catch (error) {
            this.state.message = error?.data?.message || error?.message || _t("Unable to open blind stock count check.");
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("blind_stock_count.check_pda_list", BlindStockCountCheckPdaList);

export class BlindStockCountHomepage extends Component {
    static template = "blind_stock_count.Homepage";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, access: { can_count: false, can_check: false, can_manage_work_packages: false } });
        onMounted(() => this.loadAccess());
    }

    async loadAccess() {
        try {
            this.state.access = await this.orm.call("blind.stock.count", "get_pda_home_access", []);
        } finally {
            this.state.loading = false;
        }
    }

    openPdaList() {
        this.action.doAction("blind_stock_count.action_blind_stock_count_pda_list");
    }

    openCheckPdaList() {
        this.action.doAction("blind_stock_count.action_blind_stock_count_check_pda_list");
    }

    openNewWorkPackage() {
        this.action.doAction("blind_stock_count.action_blind_stock_count_new_work_package");
    }
}

registry.category("actions").add("blind_stock_count.homepage", BlindStockCountHomepage);

export class BlindStockCountPdaList extends Component {
    static template = "blind_stock_count.PdaList";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, workPackages: [], workPackage: null, locationGroups: [], message: "" });
        onMounted(() => this.loadWorkPackages());
    }

    async loadWorkPackages() {
        this.state.loading = true;
        try {
            this.state.workPackages = await this.orm.call("blind.stock.count", "get_scannable_work_packages", []);
        } catch (error) {
            this.state.message = error?.data?.message || error?.message || _t("Unable to load blind stock count work packages.");
        } finally {
            this.state.loading = false;
        }
    }

    async selectWorkPackage(workPackage) {
        this.state.workPackage = workPackage;
        this.state.loading = true;
        try {
            const counts = await this.orm.call("blind.stock.count", "get_pda_count_list", [workPackage.id]);
            const locationGroups = new Map();
            for (const count of counts) {
                const locationGroup = locationGroups.get(count.location_id) || { id: count.location_id, name: count.location_name, counts: [], currentCountId: false };
                locationGroup.counts.push(count);
                locationGroups.set(count.location_id, locationGroup);
            }
            this.state.locationGroups = [...locationGroups.values()].map((locationGroup) => {
                locationGroup.counts.sort((left, right) => right.recount_round - left.recount_round || right.id - left.id);
                const currentCount = locationGroup.counts.find((count) => ["draft", "counting"].includes(count.state)) || locationGroup.counts.find((count) => !count.is_replaced);
                locationGroup.currentCountId = currentCount?.id || false;
                return locationGroup;
            }).sort((left, right) => left.name.localeCompare(right.name));
        } catch (error) {
            this.state.message = error?.data?.message || error?.message || _t("Unable to load blind stock counts.");
        } finally {
            this.state.loading = false;
        }
    }

    backToWorkPackages() {
        this.state.workPackage = null;
        this.state.locationGroups = [];
        this.state.message = "";
    }

    openPdaCount(count) {
        if (!["draft", "counting", "done"].includes(count.state)) {
            return;
        }
        this.action.doAction({ type: "ir.actions.client", tag: "blind_stock_count.scan", target: "main", params: { blind_stock_count_id: count.id } });
    }

    openNewCount() {
        this.action.doAction({ type: "ir.actions.client", tag: "blind_stock_count.scan", target: "main", params: { work_package_id: this.state.workPackage.id } });
    }
}

registry.category("actions").add("blind_stock_count.pda_list", BlindStockCountPdaList);
