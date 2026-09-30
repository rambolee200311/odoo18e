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
        this.onPageInteraction = () => {
            if (!this.processing && !["select_project", "input_quantity"].includes(this.state.nextStep)) {
                this.focusBarcodeInput();
            }
        };
        this.state = useState({
            loading: false,
            message: "",
            messageType: "info",
            projects: [],
            projectId: false,
            projectName: "",
            count: null,
            pallet: null,
            pallets: [],
            expandedPalletId: false,
            product: null,
            editingLineId: false,
            lastScannedLineIds: [],
            quantity: "",
            nextStep: "select_project",
        });
        onMounted(async () => {
            document.addEventListener("click", this.onPageInteraction);
            document.addEventListener("touchstart", this.onPageInteraction, { passive: true });
            if (this.continueCountId) {
                const result = await this.call("get_continue_scan_data", [this.continueCountId]);
                if (result) {
                    this.state.projectId = result.project.id;
                    this.state.projectName = result.project.name;
                    this.state.count = result.count;
                    const pallets = result.pallets || [];
                    this.state.pallets = pallets;
                    this.state.pallet = null;
                    this.state.expandedPalletId = false;
                    this.state.nextStep = "scan_pallet";
                    this.showMessage(pallets.length ? _t("Blind stock count loaded. Tap a pallet to continue or scan a new pallet.") : _t("Blind stock count loaded. Now scan a pallet."));
                }
            } else {
                await this.loadProjects();
            }
            this.focusBarcodeInput();
        });
        onPatched(() => this.onPageInteraction());
        onWillUnmount(() => {
            document.removeEventListener("click", this.onPageInteraction);
            document.removeEventListener("touchstart", this.onPageInteraction);
        });
    }

    async loadProjects() {
        const projects = await this.call("get_scannable_projects", []);
        if (projects) {
            this.state.projects = projects;
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

    selectPallet(pallet) {
        if (this.state.nextStep === "input_quantity") {
            this.showMessage(_t("Record or cancel the quantity before changing pallets."), "warning");
            return;
        }
        if (this.state.expandedPalletId === pallet.id) {
            this.state.pallet = null;
            this.state.expandedPalletId = false;
            this.state.product = null;
            this.state.editingLineId = false;
            this.state.lastScannedLineIds = [];
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
        this.state.quantity = "";
        this.state.nextStep = "scan_product";
        this.showMessage(_t("Pallet selected. Now scan a product."));
        this.focusBarcodeInput();
    }

    onProjectChange(event) {
        this.state.projectId = Number(event.target.value) || false;
        this.state.projectName = event.target.selectedOptions[0]?.text || "";
    }

    confirmProject() {
        if (!this.state.projectId) {
            this.showMessage(_t("Please select a project."), "danger");
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
        if (this.processing || this.state.nextStep === "select_project") {
            return;
        }
        if (this.state.nextStep === "input_quantity") {
            this.showMessage(_t("Record or cancel the quantity before scanning the next product."), "warning");
            return;
        }
        if (this.state.nextStep === "scan_location") {
            const result = await this.call("action_scan_location", [this.state.projectId, barcode], barcode);
            if (result) {
                this.state.count = result.count;
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
                this.state.nextStep = "scan_product";
                this.showMessage(result.message, "success");
                this.focusBarcodeInput();
            }
            return;
        }
        if (this.state.nextStep === "scan_product") {
            const result = await this.call("action_scan_product", [this.state.pallet.id, barcode], barcode);
            if (result) {
                const hasManualLine = result.product.tracking === "none" && result.product.manual_line_id;
                this.state.product = result.product;
                if (hasManualLine) {
                    const productLines = this.state.pallet.product_lines || [];
                    this.setPallet({ ...this.state.pallet, product_lines: [...productLines.filter((line) => line.id === result.product.manual_line_id), ...productLines.filter((line) => line.id !== result.product.manual_line_id)] });
                }
                this.state.editingLineId = hasManualLine || false;
                this.state.quantity = result.product.tracking === "none" ? result.product.counted_qty || "" : "";
                this.state.lastScannedLineIds = [];
                this.state.nextStep = result.product.tracking === "none" ? "input_quantity" : "scan_serial_numbers";
                this.showMessage(hasManualLine ? _t("Edit the counted quantity.") : result.product.tracking === "none" ? _t("Enter the counted quantity.") : _t("Now scan serial number(s)."), "success");
                this.focusBarcodeInput();
            }
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
        if (line.tracking !== "none") {
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

    switchProduct() {
        this.state.product = null;
        this.state.editingLineId = false;
        this.state.lastScannedLineIds = [];
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
        this.state.quantity = "";
        this.state.nextStep = "scan_pallet";
        this.showMessage(_t("Now scan a pallet."));
        this.focusBarcodeInput();
    }

    async completeCount() {
        if (!this.state.count) {
            return;
        }
        const result = await this.call("action_done", [[this.state.count.id]]);
        if (result) {
            this.state.count = null;
            this.state.pallet = null;
            this.state.pallets = [];
            this.state.expandedPalletId = false;
            this.state.product = null;
            this.state.editingLineId = false;
            this.state.lastScannedLineIds = [];
            this.state.quantity = "";
            this.state.nextStep = "scan_location";
            this.showMessage(_t("Blind stock count completed. Scan the next internal location or change the project."), "success");
            this.focusBarcodeInput();
        }
    }
}

registry.category("actions").add("blind_stock_count.scan", BlindStockCountScan);

export class BlindStockCountHomepage extends Component {
    static template = "blind_stock_count.Homepage";
    static props = { ...standardActionServiceProps };

    setup() {
        this.action = useService("action");
    }

    openScan() {
        this.action.doAction("blind_stock_count.action_blind_stock_count_scan");
    }

    openPdaList() {
        this.action.doAction("blind_stock_count.action_blind_stock_count_pda_list");
    }
}

registry.category("actions").add("blind_stock_count.homepage", BlindStockCountHomepage);

export class BlindStockCountPdaList extends Component {
    static template = "blind_stock_count.PdaList";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, counts: [], message: "" });
        onMounted(() => this.loadCounts());
    }

    async loadCounts() {
        this.state.loading = true;
        try {
            this.state.counts = await this.orm.call("blind.stock.count", "get_pda_count_list", []);
        } catch (error) {
            this.state.message = error?.data?.message || error?.message || _t("Unable to load blind stock counts.");
        } finally {
            this.state.loading = false;
        }
    }

    openPdaCount(count) {
        if (!["draft", "counting"].includes(count.state)) {
            return;
        }
        this.action.doAction({ type: "ir.actions.client", tag: "blind_stock_count.scan", target: "main", params: { blind_stock_count_id: count.id } });
    }
}

registry.category("actions").add("blind_stock_count.pda_list", BlindStockCountPdaList);
