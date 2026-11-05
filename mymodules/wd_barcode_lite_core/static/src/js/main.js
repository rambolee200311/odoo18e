/** @odoo-module **/

import { registry } from '@web/core/registry';
import { InternalTransferPage } from './internal_transfer';
import { InboundFlow } from './inbound_flow';
import { WholePalletOutboundPage } from './whole_outbound';
import { DisassemblyOutboundPage } from './disassembly_outbound';

class InboundPage extends InboundFlow {
    static template = 'stock_barcode_lite.InboundPage';
}

class WholeOutboundPage extends WholePalletOutboundPage {
    static template = 'stock_barcode_lite.WholePalletOutboundPage';
}

class BreakOutboundPage extends DisassemblyOutboundPage {
    static template = 'stock_barcode_lite.DisassemblyOutboundPage';
}

registry.category('actions').add('stock_barcode_lite_inbound', InboundPage);
registry.category('actions').add('stock_barcode_lite_outbound_whole', WholeOutboundPage);
registry.category('actions').add('stock_barcode_lite_outbound_disassembly', BreakOutboundPage);
registry.category('actions').add('wd_barcode_lite_core_inbound', InboundPage);
registry.category('actions').add('wd_barcode_lite_core_outbound_whole', WholeOutboundPage);
registry.category('actions').add('wd_barcode_lite_core_outbound_disassembly', BreakOutboundPage);
registry.category('actions').add('stock_barcode_lite_internal_transfer', InternalTransferPage);
