/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Homepage } from "./homepage";
import { ActualInboundConfirmation } from "./actual_inbound_confirmation";
import { ActualPalletBinding } from "./actual_pallet_binding";
import { OutboundPalletBinding } from "./outbound_pallet_binding";

// 组件绑定事件
registry.category("actions").add("stock_barcode_lite_homepage", Homepage);
registry.category("actions").add("stock_barcode_lite_actual_inbound_confirmation", ActualInboundConfirmation);
registry.category("actions").add("stock_barcode_lite_actual_pallet_binding", ActualPalletBinding);
registry.category("actions").add("stock_barcode_lite_outbound_pallet_binding", OutboundPalletBinding);
