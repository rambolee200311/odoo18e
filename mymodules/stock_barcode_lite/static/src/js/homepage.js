/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";

/**
 * Stock Barcode Lite - Homepage Component
 */
export class Homepage extends Component {
    static template = "stock_barcode_lite.Homepage";
    static props = {
        action: Object,
        actionId: Number,
        updateActionState: Function,
        className: String,
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
