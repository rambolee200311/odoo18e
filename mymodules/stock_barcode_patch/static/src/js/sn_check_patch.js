/** @odoo-module */

import { patch } from '@web/core/utils/patch';
import BarcodePickingModel from '@stock_barcode/models/barcode_picking_model';
import { _t } from '@web/core/l10n/translation';

const { _processBarcode } = BarcodePickingModel.prototype;

patch(BarcodePickingModel.prototype, {
    async _processBarcode(barcode) {
        // 解析条码
        const barcodeData = await this._parseBarcode(barcode);

        // 检查是否为序列号
        if (barcodeData.lot || barcodeData.lotName) {
            const lotName = barcodeData.lotName || barcodeData.lot.name;
            const product = barcodeData.product;

            if (product && product.tracking === 'serial') {
                // 检查当前picking当前产品
                for (const line of this.currentState.lines) {
                    // 只检查当前产品（跳过不同产品）
                    if (line.product_id.id !== product.id) {
                        continue;
                    }

                    const lineLotName = this.getlotName(line);
                    // 修改点：移除 qty_done 检查
                    if (lineLotName === lotName) {
                        this.notification(
                            _t("The scanned serial number %s is already used in this picking for this product.", lotName),
                            { type: 'danger' }
                        );
                        return; // 阻止后续处理
                    }
                }
            }
        }

        // 调用原生方法（原生方法中的重复检查不会再触发，因为条件更严格）
        return _processBarcode.call(this, barcode);
    },
});