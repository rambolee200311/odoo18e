/** @odoo-module **/

import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

/**
 * WorldDepot customizations:
 * - When there is no reservation, use the related move demand (`product_uom_qty`) as the target qty.
 * - Prevent scanning quantities (incl. multi-barcode / multi-SN) beyond the move demand.
 *
 * Important: we patch the official model instead of editing `stock_barcode` sources.
 */
patch(BarcodePickingModel.prototype, {
    /**
     * Demand qty used by WorldDepot rules:
     * 1) If reserved => reserved qty
     * 2) Else => move.product_uom_qty
     */
    getQtyDemand1(line) {
        if (line.reserved_uom_qty) {
            return line.reserved_uom_qty;
        }
        if (line.move_id) {
            const move = this.cache.getRecord("stock.move", line.move_id);
            if (move?.product_uom_qty) {
                return move.product_uom_qty;
            }
        }
        return 0;
    },

    async processBarcode(barcode, options = {}) {
        // console.log(barcode,'barcode')
        if (!barcode) {
            return;
        }
    
        const barcodes = this.splitBarcode(barcode);
        const contextLine = this.selectedLine || this.lastScannedLine;
    
        if (barcodes.length > 1 && contextLine && contextLine.product_id.tracking === "serial") {
            const parentLine = this._getParentLine(contextLine) || contextLine;
            const moveId = parentLine.move_id;
            const demandQty = this.getQtyDemand1(parentLine);
    
            if (demandQty > 0) {
                const totalDoneForMove = this.currentState.lines.reduce((sum, l) => {
                    if (l.product_id.id !== parentLine.product_id.id || l.move_id !== moveId) {
                        return sum;
                    }
                    if (parentLine.reserved_uom_qty) {
                        // With reservation: count parent line + unreserved siblings (same move).
                        if (l.virtual_id === parentLine.virtual_id || !l.reserved_uom_qty) {
                            return sum + (l.qty_done || 0);
                        }
                        return sum;
                    }
                    // Without reservation: count all lines on the move.
                    return sum + (l.qty_done || 0);
                }, 0);
    
                // 修复点1：计算剩余可扫量
                const remainingQty = demandQty - totalDoneForMove;
                // 修复点2：校验本次扫描数是否超过剩余可扫量
                if (barcodes.length > remainingQty) {
                    const message = _t(
                        "Remaining demand is %(remaining)s, but this scan contains %(scanQty)s serial numbers. You can only scan %(remaining)s more.",
                        { remaining: remainingQty, scanQty: barcodes.length }
                    );
                    this.notification(message, {
                        title: _t("Quantity exceeds demand"),
                        type: "danger",
                    });
                    return;
                }
            }
        }
    
        return super.processBarcode(barcode, options);
    },

    /**
     * Per-increment guard (covers manual increments + single SN scans).
     * Keeps official UoM conversion + serial constraint, adds demand constraint.
     */
    _updateLineQty(line, args) {
        if (!args.qty_done) {
            return;
        }

        const lineNextQty = (line.qty_done || 0) + args.qty_done;

        // 2) Serial products: cannot exceed 1 per serial line.
        if (
            line.product_id.tracking === "serial" &&
            (this.record.use_create_lots || this.record.use_existing_lots) &&
            lineNextQty > 1
        ) {
            return;
        }

        // 3) Demand constraint at move level (aligned with validate() aggregation logic).
        const parentLine = this._getParentLine(line) || line;
        const moveId = parentLine.move_id;
        const demandQty = this.getQtyDemand1(parentLine);
        if (demandQty > 0) {
            // const totalDoneForMove = this.currentState.lines.reduce((sum, l) => {
            //     if (l.product_id.id !== parentLine.product_id.id || l.move_id !== moveId) {
            //         return sum;
            //     }
            //     if (parentLine.reserved_uom_qty) {
            //         if (l.virtual_id === parentLine.virtual_id || !l.reserved_uom_qty) {
            //             return sum + (l.qty_done || 0);
            //         }
            //         return sum;
            //     }
            //     return sum + (l.qty_done || 0);
            // }, 0);

            const totalDoneForMove = this.currentState.lines.reduce((sum, l) => {
                //  只统计：同产品 + 同move
                if (l.product_id.id === parentLine.product_id.id && l.move_id === moveId) {
                    if (parentLine.reserved_uom_qty) {
                        if (l.virtual_id === parentLine.virtual_id || !l.reserved_uom_qty) {
                            return sum + (l.qty_done || 0);
                        }
                        return sum;
                    }
                    return sum + (l.qty_done || 0);
                }
                return sum;
            }, 0);

            const nextTotalDoneForMove = totalDoneForMove + args.qty_done;
            if (nextTotalDoneForMove > demandQty) {
                const message = _t(
                    "Demand is %(demand)s, done would be %(done)s. You cannot add more.",
                    { demand: demandQty, done: nextTotalDoneForMove }
                );
                return this.notification(message, { title: _t("Quantity exceeds demand"), type: "danger" });
            }
        }

        // 4) Write qty.
        line.qty_done = lineNextQty;
        this._setUser();
    },
});

