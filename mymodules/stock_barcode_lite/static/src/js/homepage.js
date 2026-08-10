/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
/**
 * Stock Barcode Lite - Homepage Component
 */
export class Homepage extends Component {
    static template = "stock_barcode_lite.Homepage";
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        updateActionState: { type: Function, optional: true },
        className: { type: String, optional: true },
    };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
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
        try {
            const result = await this.orm.call(
                "stock.picking",
                "action_create_pda_internal_transfer",
                []
            );
            if (result) {
//                console.log('嘿嘿',result)
                if (result.type === "ir.actions.client") {
                    this.action.doAction(result);
                }
            }
        } catch (error) {
            console.error("Failed to create internal transfer:", error);
        }
    }
}
