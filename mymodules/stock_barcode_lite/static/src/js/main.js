/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Homepage } from "./homepage";
import { InboundFlow } from "./inbound_flow";
import { WholePalletOutboundPage } from "./whole_outbound";
import { DisassemblyOutboundPage } from "./disassembly_outbound";

class InboundPage extends InboundFlow {
    static template = "stock_barcode_lite.InboundPage";
}

class BreakOutboundPage extends DisassemblyOutboundPage {
    static template = "stock_barcode_lite.DisassemblyOutboundPage";
}

class WholeOutboundPage extends WholePalletOutboundPage {
    static template = "stock_barcode_lite.WholePalletOutboundPage";
}

// 组件绑定事件
registry.category("actions").add("stock_barcode_lite_homepage", Homepage);
registry.category("actions").add("stock_barcode_lite_inbound", InboundPage);
registry.category("actions").add("stock_barcode_lite_outbound_disassembly", BreakOutboundPage);
registry.category("actions").add("stock_barcode_lite_outbound_whole", WholeOutboundPage);
