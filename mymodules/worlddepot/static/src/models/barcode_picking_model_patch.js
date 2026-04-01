/** @odoo-module **/

import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { formatFloat } from "@web/core/utils/numbers";

function _moveIdRaw(moveId) {
    return moveId?.id ?? moveId;
}

patch(BarcodePickingModel.prototype, {
    // =====================================================================================
    // 1. 只给【超额分组父行】隐藏分母，正常需求行永远显示 0/10 这种格式
    // =====================================================================================
    getQtyDemand(line) {
        if (line.isExcessGroup) {
            return false;
        }
        return super.getQtyDemand(...arguments);
    },

    // =====================================================================================
    // 2. 独立groupKey，不冲突
    // =====================================================================================
    groupKey(line) {
        const base = super.groupKey(...arguments);
        return line.isExcessGroup ? `${base}_ex` : base;
    },

    // =====================================================================================
    // 3. 构建分组（绝对解决空数组报错）
    // =====================================================================================
    _buildSplitGroupedLine(sublines, originalDemand, isExcess, opened) {
        if (!sublines || sublines.length === 0) return null;

        const ids = sublines.map(s => s.id);
        const virtual_ids = sublines.map(s => s.virtual_id);
        const qtyDone = sublines.reduce((sum, s) => sum + (s.qty_done || 0), 0);

        const groupedLine = this._groupSublines(sublines, ids, virtual_ids, originalDemand, qtyDone);
        groupedLine.opened = opened;
        groupedLine.isExcessGroup = isExcess;
        return groupedLine;
    },

    // =====================================================================================
    // 4. 核心分组逻辑：
    // 不报错 + 需求行永远显示分母 + 无超额不显示超额行
    // =====================================================================================
    groupLines() {
        super.groupLines();
        if (!this.groupingLinesEnabled) {
            this._scheduleOverdoneDomSync();
            return this._groupedLines;
        }

        const newGrouped = [];

        for (const groupLine of this._groupedLines) {
            const sublines = groupLine.lines;
            if (!sublines?.length) {
                newGrouped.push(groupLine);
                continue;
            }

            const tracking = groupLine.product_id?.tracking;
            if (!["serial", "lot"].includes(tracking)) {
                newGrouped.push(groupLine);
                continue;
            }

            const totalDemand = groupLine.reserved_uom_qty || 0;
            const totalDone = sublines.reduce((sum, l) => sum + (l.qty_done || 0), 0);
            const hasRealExcess = totalDone > totalDemand;

            const realExcessLines = [];
            const normalDemandLines = [];

            for (const sub of sublines) {
                if (sub.reserved_uom_qty === 0 && sub.qty_done > 0 && hasRealExcess) {
                    realExcessLines.push(sub);
                } else {
                    normalDemandLines.push(sub);
                }
            }

            // 无超额 → 不拆分
            if (realExcessLines.length === 0) {
                newGrouped.push(groupLine);
                continue;
            }

            // 有超额 → 拆分成两组
            const excessGroup = this._buildSplitGroupedLine(realExcessLines, totalDemand, true, true);
            const demandGroup = this._buildSplitGroupedLine(normalDemandLines, totalDemand, false, false);

            if (excessGroup) newGrouped.push(excessGroup);
            if (demandGroup) newGrouped.push(demandGroup);
        }

        this._groupedLines = this._sortLine(newGrouped);
        this._scheduleOverdoneDomSync();
        return this._groupedLines;
    },

    // =====================================================================================
    // 原生方法，完全不动
    // =====================================================================================
    _getMoveLineData(id) {
        const smlData = this.cache.getRecord('stock.move.line', id);
        smlData.dummy_id = smlData.dummy_id && Number(smlData.dummy_id);
        let prevLine = this.currentState?.lines.find(line => line.id === id);
        if (!prevLine && smlData.dummy_id) {
            prevLine = this.currentState?.lines.find(line => line.virtual_id === smlData.dummy_id);
        }
        const previousVirtualId = prevLine && prevLine.virtual_id;
        smlData.virtual_id = smlData.dummy_id || previousVirtualId || this._uniqueVirtualId;
        smlData.product_id = this.cache.getRecord('product.product', smlData.product_id);
        smlData.product_uom_id = this.cache.getRecord('uom.uom', smlData.product_uom_id);
        smlData.location_id = this.cache.getRecord('stock.location', smlData.location_id);
        smlData.location_dest_id = this.cache.getRecord('stock.location', smlData.location_dest_id);
        smlData.lot_id = smlData.lot_id && this.cache.getRecord('stock.lot', smlData.lot_id);
        smlData.owner_id = smlData.owner_id && this.cache.getRecord('res.partner', smlData.owner_id);
        smlData.package_id = smlData.package_id && this.cache.getRecord('stock.quant.package', smlData.package_id);
        smlData.product_packaging_id = smlData.product_packaging_id && this.cache.getRecord('product.packaging', smlData.product_packaging_id);

        if (this.reloadingMoveLines) {
            if (prevLine) {
                smlData.sortIndex = prevLine.sortIndex;
                if (smlData.quantity && !smlData.qty_done) {
                    smlData.reserved_uom_qty = smlData.quantity;
                } else {
                    if (smlData.product_uom_id.id !== prevLine.product_uom_id.id) {
                        const params = { digits: [false, this.precision] };
                        const baseQty = (prevLine.reserved_uom_qty / prevLine.product_uom_id.factor) * smlData.product_uom_id.factor;
                        smlData.reserved_uom_qty = parseFloat(formatFloat(baseQty, params));
                    } else {
                        smlData.reserved_uom_qty = prevLine.reserved_uom_qty;
                    }
                }
            } else {
                smlData.qty_done = smlData.quantity;
                smlData.reserved_uom_qty = 0;
            }
        } else {
            smlData.reserved_uom_qty = smlData.quantity;
        }

        const resultPackage = smlData.result_package_id && this.cache.getRecord('stock.quant.package', smlData.result_package_id);
        if (resultPackage) {
            smlData.result_package_id = resultPackage;
            const packageType = resultPackage && resultPackage.package_type_id;
            resultPackage.package_type_id = packageType && this.cache.getRecord('stock.package.type', packageType);
        }

        this._scheduleOverdoneDomSync();
        return smlData;
    },

    _updateLineQty(line, args) {
        const tracking = line.product_id?.tracking;
        if (args.qty_done) {
            if (tracking === "serial") {
                const nextQty = (line.qty_done || 0) + args.qty_done;
                if (nextQty > 1) return;
            }
            line.qty_done = (line.qty_done || 0) + args.qty_done;
            this._setUser();
        }

        const parentLine = this._getParentLine(line) || line;
        const moveRaw = _moveIdRaw(parentLine.move_id);
        const move = moveRaw && this.cache.getRecord("stock.move", moveRaw);
        const moveDemand = move?.product_uom_qty || 0;

        if (moveDemand > 0) {
            const totalDone = this.currentState.lines.reduce((sum, l) => {
                if (l.product_id?.id === parentLine.product_id?.id && l.move_id === parentLine.move_id) {
                    return sum + (l.qty_done || 0);
                }
                return sum;
            }, 0);
            if (totalDone > moveDemand) {
                this.notification(_t("Caution: Total quantity exceeds demand."), { type: "danger" });
            }
        }

        this._scheduleOverdoneDomSync();
    },

    _scheduleOverdoneDomSync() {
        if (!this._overdoneDomSyncDelays) {
            this._overdoneDomSyncDelays = [0, 50, 150, 350, 600, 1000];
        }
        for (const ms of this._overdoneDomSyncDelays) {
            setTimeout(() => this._syncOverdoneDomHighlights(), ms);
        }
    },

    _lineDemandQty(line) {
        return this.getQtyDemand(line);
    },

    _syncOverdoneDomHighlights() {
        document.querySelectorAll(".o_barcode_line").forEach(el => {
            el.classList.remove("o_overdone_line", "text-danger", "fw-bold");
            el.style.removeProperty("background-color");
            el.style.removeProperty("color");
            el.style.removeProperty("font-weight");
        });

        document.querySelectorAll(".o_barcode_line.o_excess_group").forEach(root => {
            root.classList.add("o_overdone_line");
            root.style.setProperty("background-color", "rgba(220, 53, 69, 0.12)", "important");

            root.querySelectorAll(".o_sublines .o_barcode_line").forEach(sub => {
                sub.classList.add("o_overdone_line");
                sub.style.setProperty("background-color", "rgba(220, 53, 69, 0.07)", "important");
            });

            root.querySelectorAll(".qty-done").forEach(el => {
                el.classList.add("text-danger", "fw-bold");
                el.style.setProperty("color", "#dc3545", "important");
            });
        });
    },
});