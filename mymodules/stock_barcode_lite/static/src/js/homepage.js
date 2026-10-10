/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

/**
 * Stock Barcode Lite - Homepage Component
 */
export class Homepage extends Component {
    static template = "stock_barcode_lite.Homepage";
    static props = { ...standardActionServiceProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this._creatingInternalTransfer = false;
    }

    _onInboundClick() {
        this.action.doAction("stock_barcode_lite_inbound");
    }

    _onOutboundBreakClick() {
        this.action.doAction("stock_barcode_lite_outbound_disassembly");
    }

    _onOutboundWholeClick() {
        this.action.doAction("stock_barcode_lite_outbound_whole");
    }

    async _onInternalTransferClick() {
        if (this._creatingInternalTransfer) {
            return;
        }

        this._creatingInternalTransfer = true;
        try {
            const result = await this.orm.call(
                "stock.picking",
                "action_create_pda_internal_transfer",
                []
            );

            if (result?.type === "ir.actions.client") {
                await this.action.doAction(result);
            }
        } catch (error) {
            console.error("Failed to create internal transfer:", error);
        } finally {
            this._creatingInternalTransfer = false;
        }
    }

    _onActualInboundConfirmationClick() {
        this.action.doAction("stock_barcode_lite_actual_inbound_confirmation");
    }
}