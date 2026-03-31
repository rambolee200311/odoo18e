/** @odoo-module **/

import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { formatFloat } from "@web/core/utils/numbers";

function _moveIdRaw(moveId) {
    return moveId?.id ?? moveId;
}

// Patch BarcodePickingModel
patch(BarcodePickingModel.prototype, {
    beforeQuit() {
        return super.beforeQuit();
    },

    getQtyDemand(line) {
        const parentLine = this._getParentLine(line) || line;
        if (line.virtual_demand_qty || parentLine.virtual_demand_qty) {
            return line.virtual_demand_qty || parentLine.virtual_demand_qty;
        }
        if (line.reserved_uom_qty) {
            return line.reserved_uom_qty;
        }
        if (line.move_id) {
            const move = this.cache.getRecord("stock.move", line.move_id);
            return move?.product_uom_qty || 0;
        }
        return 0;
    },

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
                const smlMoveId = _moveIdRaw(smlData.move_id);
                const storageKey = `virtual_demand_${this.resId}_${smlMoveId}`;
                const storedDemand = sessionStorage.getItem(storageKey);
                if (storedDemand !== null) {
                    smlData.virtual_demand_qty = parseFloat(storedDemand);
                } else if (prevLine.virtual_demand_qty) {
                    smlData.virtual_demand_qty = prevLine.virtual_demand_qty;
                }
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
                const smlMoveId = _moveIdRaw(smlData.move_id);
                const storageKey = `virtual_demand_${this.resId}_${smlMoveId}`;
                const storedDemand = sessionStorage.getItem(storageKey);
                if (storedDemand !== null) {
                    smlData.virtual_demand_qty = parseFloat(storedDemand);
                } else {
                    smlData.virtual_demand_qty = smlData.reserved_uom_qty || smlData.quantity;
                }
                smlData.qty_done = smlData.quantity;
                smlData.reserved_uom_qty = 0;
            }
        } else {
            const smlMoveId = _moveIdRaw(smlData.move_id);
            const storageKey = `virtual_demand_${this.resId}_${smlMoveId}`;
            const storedDemand = sessionStorage.getItem(storageKey);
            if (storedDemand !== null) {
                smlData.virtual_demand_qty = parseFloat(storedDemand);
            } else {
                smlData.virtual_demand_qty = smlData.reserved_uom_qty || smlData.quantity;
            }
            smlData.reserved_uom_qty = smlData.quantity;
        }

        const resultPackage = smlData.result_package_id && this.cache.getRecord('stock.quant.package', smlData.result_package_id);
        if (resultPackage) {
            smlData.result_package_id = resultPackage;
            const packageType = resultPackage && resultPackage.package_type_id;
            resultPackage.package_type_id = packageType && this.cache.getRecord('stock.package.type', packageType);
        }

        // 加载 line 完成后，触发超量高亮同步
        this._scheduleOverdoneDomSync();

        return smlData;
    },

    _updateLineQty(line, args) {
        if (!args.qty_done) return;

        const lineNextQty = (line.qty_done || 0) + args.qty_done;

        if (line.product_id.tracking === "serial" && lineNextQty > 1) {
            return;
        }

        const parentLine = this._getParentLine(line) || line;

        if (!parentLine.virtual_demand_qty) {
            const demandQty = this.getQtyDemand(parentLine);
            parentLine.virtual_demand_qty = demandQty;
        }

        const demandQty = this.getQtyDemand(parentLine);

        if (demandQty > 0) {
            const moveKey = _moveIdRaw(parentLine.move_id) || parentLine.id;
            const storageKey = `virtual_demand_${this.resId}_${moveKey}`;
            sessionStorage.setItem(storageKey, String(demandQty));

            const totalDoneForMove = this.currentState.lines.reduce((sum, l) => {
                if (l.product_id.id === parentLine.product_id.id && l.move_id === parentLine.move_id) {
                    if (!parentLine.reserved_uom_qty || l.virtual_id === parentLine.virtual_id || !l.reserved_uom_qty) {
                        return sum + (l.qty_done || 0);
                    }
                }
                return sum;
            }, 0);

            const nextTotal = totalDoneForMove + args.qty_done;

            if (nextTotal > demandQty) {
                this.notification(_t("Caution: Total quantity exceeds demand."), { type: "warning" });
            }
        }

        line.qty_done = lineNextQty;

        if (!line.reserved_uom_qty && line.move_id) {
            line.virtual_demand_qty = demandQty;
        }

        this._setUser();
        this._scheduleOverdoneDomSync();
    },

    _scheduleOverdoneDomSync() {
        if (!this._overdoneDomSyncDelays) {
            this._overdoneDomSyncDelays = [0, 50, 150, 350, 600];
        }
        for (const ms of this._overdoneDomSyncDelays) {
            window.setTimeout(() => this._syncOverdoneDomHighlights(), ms);
        }
    },

    _lineDemandQty(line) {
        return this.getQtyDemand(line);
    },

    _syncOverdoneDomHighlights() {
        const stateLines = this.currentState?.lines;
        if (!stateLines?.length) {
            return;
        }

        const groups = new Map();
        for (const l of stateLines) {
            const moveId = l.move_id;
            const productId = l.product_id?.id;
            if (!moveId || !productId) {
                continue;
            }
            const key = `${moveId}|${productId}`;
            if (!groups.has(key)) {
                const parent = this._getParentLine(l) || l;
                const demand = this._lineDemandQty(parent);
                groups.set(key, { demand, totalDone: 0, virtualIds: new Set(), moveId, productId });
            }
            const g = groups.get(key);
            g.totalDone += l.qty_done || 0;
            if (l.virtual_id !== undefined && l.virtual_id !== null) {
                g.virtualIds.add(String(l.virtual_id));
            }
        }

        const overVirtualIds = new Set();
        for (const [, g] of groups) {
            if (g.demand > 0 && g.totalDone > g.demand) {
                for (const vid of g.virtualIds) {
                    overVirtualIds.add(vid);
                }
            }
        }

        const clearQtyStyle = (el) => {
            el.classList.remove("text-danger", "fw-bold");
            el.style.removeProperty("color");
            el.style.removeProperty("font-weight");
        };

        document.querySelectorAll(".o_barcode_line").forEach((el) => {
            const vid = el.dataset.virtualId;
            if (vid === undefined || vid === null || vid === "") {
                return;
            }
            const isOver = overVirtualIds.has(String(vid));

            el.classList.toggle("o_overdone_line", isOver);
            if (isOver) {
                el.style.setProperty("background-color", "rgba(220, 53, 69, 0.1)", "important");
            } else {
                el.style.removeProperty("background-color");
            }

            el.querySelectorAll(".qty-done, [class*='qty']").forEach(clearQtyStyle);
            const qtyEl =
                el.querySelector(".qty-done") ||
                el.querySelector("[class*='qty-done']") ||
                [...el.querySelectorAll("span, div")].find((node) => /\d+\s*\/\s*\d+/.test((node.textContent || "").trim()));

            if (isOver && qtyEl) {
                qtyEl.classList.add("text-danger", "fw-bold");
                qtyEl.style.setProperty("color", "#dc3545", "important");
                qtyEl.style.setProperty("font-weight", "700", "important");
            } else if (qtyEl) {
                clearQtyStyle(qtyEl);
            }
        });
    },
});
