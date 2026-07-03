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
}
