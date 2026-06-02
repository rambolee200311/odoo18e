/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Homepage } from "./components/homepage";
import { InboundFlow } from "./components/inbound_flow";
import { OutboundFlow } from "./components/outbound_flow";

class InboundPage extends InboundFlow {
    static template = "stock_barcode_lite.InboundPage";
}

class OutboundPage extends OutboundFlow {
    static template = "stock_barcode_lite.OutboundPage";
}

// 组件绑定事件
registry.category("actions").add("stock_barcode_lite_homepage", Homepage);
registry.category("actions").add("stock_barcode_lite_inbound", InboundPage);
registry.category("actions").add("stock_barcode_lite_outbound", OutboundPage);

console.log('[stock_barcode_lite] All pages registered');
