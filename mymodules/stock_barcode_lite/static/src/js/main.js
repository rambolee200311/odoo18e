/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Homepage } from "./homepage";
import { InboundFlow } from "./inbound_flow";
import { OutboundFlow } from "./outbound_flow";
import { WholePalletOutboundPage } from "./whole_outbound";

class InboundPage extends InboundFlow {
    static template = "stock_barcode_lite.InboundPage";
}

class OutboundPage extends OutboundFlow {
    static template = "stock_barcode_lite.OutboundPage";
}

class WholeOutboundPage extends WholePalletOutboundPage {
    static template = "stock_barcode_lite.WholePalletOutboundPage";
}

// 组件绑定事件
registry.category("actions").add("stock_barcode_lite_homepage", Homepage);
registry.category("actions").add("stock_barcode_lite_inbound", InboundPage);
registry.category("actions").add("stock_barcode_lite_outbound", OutboundPage);
registry.category("actions").add("stock_barcode_lite_outbound_whole", WholeOutboundPage);

console.log('[stock_barcode_lite] All pages registered');
