/** @odoo-module */

import { patch } from '@web/core/utils/patch';
import { StockBarcodeKanbanController } from '@stock_barcode/kanban/stock_barcode_kanban_controller';
import { useService } from '@web/core/utils/hooks';

const { openRecord } = StockBarcodeKanbanController.prototype;

patch(StockBarcodeKanbanController.prototype, {
    openRecord(record) {
//        console.log(record)
        if (record.data.barcode_scan_mode != 'native') {
            this.model.notification.add(
                "This picking order is managed via the custom barcode workflow. Please perform scanning operations on the custom barcode interface.",
                { type: 'danger', title: 'Prohibited Operation' }
            );
            return;
        }

        return openRecord.call(this, record);
    },
});
