/** @odoo-module */

import { patch } from '@web/core/utils/patch';
import BarcodePickingModel from '@stock_barcode/models/barcode_picking_model';
import { _t } from '@web/core/l10n/translation';

const { _processBarcode, _findLine } = BarcodePickingModel.prototype;

patch(BarcodePickingModel.prototype, {

    // ── 补丁1：SN重复检查 ──
    // 只拦截"已确认"的SN（qty_done > 0），不拦截预留行
    async _processBarcode(barcode) {
        const barcodeData = await this._parseBarcode(barcode);

        console.group('[SN_PATCH] _processBarcode');
        console.log('barcode:', barcode);
        console.log('barcodeData.lot:', barcodeData.lot);
        console.log('barcodeData.lotName:', barcodeData.lotName);
        console.log('barcodeData.product:', barcodeData.product);
        console.log('barcodeData.match:', barcodeData.match);

        if (barcodeData.lot || barcodeData.lotName) {
            const lotName = barcodeData.lotName || (barcodeData.lot && barcodeData.lot.name);

            // 三级回退确定产品
            let product = barcodeData.product;
            if (!product && barcodeData.lot && barcodeData.lot.product_id) {
                product = this.cache.getRecord('product.product', barcodeData.lot.product_id);
                console.log('product from lot.product_id:', product);
            }
            if (!product) {
                const refLine = this.selectedLine || this.lastScannedLine;
                if (refLine && refLine.product_id) {
                    product = refLine.product_id;
                    console.log('product from selectedLine/lastScannedLine:', product);
                }
            }

            console.log('resolved lotName:', lotName, '| product:', product, '| tracking:', product && product.tracking);

            if (product && product.tracking === 'serial' && lotName) {
                const linesInfo = [];
                let blocked = false;
                for (const line of this.currentState.lines) {
                    if (line.product_id.id !== product.id) continue;
                    const lineLotName = this.getlotName(line);
                    const qtyDone = this.getQtyDone(line);
                    linesInfo.push({
                        virtual_id: line.virtual_id,
                        lot_id: line.lot_id ? line.lot_id.name : null,
                        lot_name: line.lot_name,
                        qty_done: qtyDone,
                        lineLotName: lineLotName,
                        match: lineLotName === lotName,
                    });
                    // 关键：只检查 qty_done > 0 的行
                    if (qtyDone > 0 && lineLotName === lotName) {
                        console.warn('[SN_PATCH] BLOCKED - already confirmed:', lotName);
                        blocked = true;
                        this.notification(
                            _t("The scanned serial number %s is already used in this picking for this product.", lotName),
                            { type: 'danger' }
                        );
                        console.groupEnd();
                        return;
                    }
                }
                console.table(linesInfo);
                if (!blocked) {
                    console.log('[SN_PATCH] PASSED - calling original _processBarcode');
                }
            } else {
                console.log('[SN_PATCH] SKIP check - product/tracking/lotName missing');
            }
        } else {
            console.log('[SN_PATCH] SKIP - no lot or lotName in barcodeData');
        }

        console.groupEnd();
        return _processBarcode.call(this, barcode);
    },

    // ── 补丁2：确保 _findLine 优先返回预留行 ──
    // 解决因 location 不匹配导致 _findLine 选错行的问题
    _findLine(barcodeData) {
        const result = _findLine.call(this, barcodeData);

        const { lot, lotName, product } = barcodeData;
        const dataLotName = lotName || (lot && lot.name) || false;

        console.group('[SN_PATCH] _findLine');
        console.log('dataLotName:', dataLotName, '| product:', product, '| tracking:', product && product.tracking);
        console.log('original _findLine result:', result ? {
            virtual_id: result.virtual_id,
            lot_id: result.lot_id ? result.lot_id.name : null,
            lot_name: result.lot_name,
            qty_done: this.getQtyDone(result),
            location_id: result.location_id ? result.location_id.name : null,
        } : null);

        if (dataLotName && product && product.tracking === 'serial') {
            // 检查 result 是否已经是匹配的预留行
            if (result && result.product_id.id === product.id &&
                this.getQtyDone(result) === 0 && this.getlotName(result) === dataLotName) {
                console.log('[SN_PATCH] _findLine OK - result is already the reserved line');
                console.groupEnd();
                return result;
            }
            // 否则，主动查找预留行
            for (const line of this.currentState.lines) {
                if (line.product_id.id !== product.id) continue;
                if (this.getQtyDone(line) === 0 && this.getlotName(line) === dataLotName) {
                    console.warn('[SN_PATCH] _findLine OVERRIDE - returning reserved line:', {
                        virtual_id: line.virtual_id,
                        lot_id: line.lot_id ? line.lot_id.name : null,
                        lot_name: line.lot_name,
                        location_id: line.location_id ? line.location_id.name : null,
                    });
                    console.log('was going to return:', result ? result.virtual_id : null);
                    console.groupEnd();
                    return line;
                }
            }
            console.log('[SN_PATCH] _findLine - no reserved line found, using original result');
        } else {
            console.log('[SN_PATCH] _findLine - not serial tracking or no lotName, skip');
        }

        console.groupEnd();
        return result;
    },
});
