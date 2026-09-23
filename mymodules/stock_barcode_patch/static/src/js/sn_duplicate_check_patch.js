/** @odoo-module **/

import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(BarcodePickingModel.prototype, {
    /**
     * Override _processBarcode to check for SN duplicate with outbound orders
     */
    async _processBarcode(barcode) {
        // First, let the original method process the barcode
        const result = await super._processBarcode(...arguments);
        
        // Check if the scanned barcode is a serial number (lot)
        // We can check if the last scanned line has a lot_id
        const lastLine = this.lastScannedLine;
        if (lastLine && lastLine.lot_id) {
            const sn = lastLine.lot_id.name || lastLine.lot_name;
            const productId = lastLine.product_id.id;
            
            // Call backend method to check for duplicate
            try {
                const isDuplicate = await this.orm.call(
                    'stock.picking',
                    'check_sn_duplicate_for_barcode',
                    [this.record.id, sn, productId]
                );

                if (isDuplicate) {
                    // Show error notification
                    this.notification(
                        _t("Serial number \"" + sn + "\" has already been used in outbound orders. Please use a different serial number."),
                        { type: 'danger', title: _t('Duplicate Serial Number') }
                    );
                    
                    // Optionally, we could try to revert the last scan
                    // For now, we just show the warning
                }
            } catch (error) {
                console.error('Error checking SN duplicate:', error);
            }
        }
        
        return result;
    },
});
