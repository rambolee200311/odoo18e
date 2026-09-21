/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class ActualInboundConfirmation extends Component {
    static template = "stock_barcode_lite.ActualInboundConfirmationPage";
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
        });

        this._boundOnBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundOnBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundOnBarcodeBlur = this._onBarcodeBlur.bind(this);
        this._messageTimer = null;

        onMounted(() => {
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.addEventListener("input", this._boundOnBarcodeInput);
                barcodeInput.addEventListener("keydown", this._boundOnBarcodeKeydown);
                barcodeInput.addEventListener("blur", this._boundOnBarcodeBlur);
                this._focusBarcodeInput();
            }
        });

        onWillUnmount(() => {
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.removeEventListener("input", this._boundOnBarcodeInput);
                barcodeInput.removeEventListener("keydown", this._boundOnBarcodeKeydown);
                barcodeInput.removeEventListener("blur", this._boundOnBarcodeBlur);
            }
            clearTimeout(this._messageTimer);
        });
    }

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

    _onBarcodeBlur() {
        setTimeout(() => this._focusBarcodeInput(), 0);
    }

    _focusBarcodeInput() {
        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
        }
    }

    async onBarcodeScanned(barcode) {
        if (this.state.loading) return;
        this.state.loading = true;
        this.showMessage(_t("Processing..."), "info");

        try {
            const result = await this.orm.call(
                "world.depot.inbound.order",
                "action_open_actual_inbound_confirmation_wizard_by_barcode",
                [barcode]
            );
            if (result) {
                this.action.doAction(result);
            }
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
            this._focusBarcodeInput();
        } finally {
            this.state.loading = false;
        }
    }

    exit() {
        this.action.doAction("stock_barcode_lite_homepage");
    }

    showMessage(text, type = "info") {
        this.state.message = text;
        this.state.messageType = type;
        clearTimeout(this._messageTimer);
        if (type !== "danger") {
            this._messageTimer = setTimeout(() => {
                if (this.state.message === text) {
                    this.state.message = "";
                }
            }, 4000);
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
}