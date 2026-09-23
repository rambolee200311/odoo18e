/** @odoo-module **/

import { BaseBarcodePage } from "./base_barcode_page";
import { _t } from "@web/core/l10n/translation";

export class ActualInboundConfirmation extends BaseBarcodePage {
    static template = "stock_barcode_lite.ActualInboundConfirmationPage";
    static props = {};

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

}