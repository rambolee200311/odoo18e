/** @odoo-module **/

import GroupedLineComponent from "@stock_barcode/components/grouped_line";
import { patch } from "@web/core/utils/patch";

patch(GroupedLineComponent.prototype, {
    get componentClasses() {
        const base = super.componentClasses;
        return this.line.isExcessGroup ? `${base} o_excess_group`.trim() : base;
    },
});
