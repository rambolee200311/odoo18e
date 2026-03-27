/** @odoo-module **/

import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

// Patch BarcodePickingModel
patch(BarcodePickingModel.prototype, {
    getQtyDemand1(line) {
        if (line.reserved_uom_qty) return line.reserved_uom_qty;
        if (line.move_id) {
            const move = this.cache.getRecord("stock.move", line.move_id);
            return move?.product_uom_qty || 0;
        }
        return 0;
    },

    _updateLineQty(line, args) {
        if (!args.qty_done) return;

        const lineNextQty = (line.qty_done || 0) + args.qty_done;

        if (line.product_id.tracking === "serial" && lineNextQty > 1) {
            return;
        }

        const parentLine = this._getParentLine(line) || line;
        const demandQty = this.getQtyDemand1(parentLine);

        if (demandQty > 0) {
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

        // OWL re-renders after _setUser and wipes inline styles; also over-demand is often split
        // across several lines (each qty_done <= demand) — compare move+product totals instead.
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
        if (line.reserved_uom_qty) {
            return line.reserved_uom_qty;
        }
        if (line.virtual_demand_qty) {
            return line.virtual_demand_qty;
        }
        return this.getQtyDemand1(this._getParentLine(line) || line);
    },

    _syncOverdoneDomHighlights() {
        const stateLines = this.currentState?.lines;
        if (!stateLines?.length) {
            return;
        }

        // Group by move + product: total done vs single demand for that move
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
                groups.set(key, { demand, totalDone: 0, virtualIds: new Set() });
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
