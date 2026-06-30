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
