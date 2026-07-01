/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { useSortable } from "@web/core/utils/sortable_owl";
import { ListRenderer } from "@web/views/list/list_renderer";

const COLUMN_ORDER_PREFIX = "column_reorder_tspl.columns,";

function getColumnKey(column) {
    return String(column.id || column.name || "");
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.keyColumnOrder = `${COLUMN_ORDER_PREFIX}${this.createViewKey()}`;
        this.columnOrder = this.loadColumnOrder();

        useSortable({
            enable: () =>
                !this.env.isSmall &&
                !this.editedRecord &&
                this.columns.filter((column) => column.type === "field" && column.hasLabel).length > 1,
            ref: this.rootRef,
            elements: ".o_column_reorder_header",
            handle: ".o_column_reorder_handle",
            cursor: "grabbing",
            onDragStart: () => {
                this.preventReorder = true;
            },
            onDrop: ({ element, previous, next }) => {
                this.onColumnReorderDrop(element, previous, next);
            },
        });
    },

    getActiveColumns(list) {
        return this.sortColumnsBySavedOrder(super.getActiveColumns(list));
    },

    loadColumnOrder() {
        const rawOrder = browser.localStorage.getItem(this.keyColumnOrder);
        if (!rawOrder) {
            return [];
        }
        try {
            return JSON.parse(rawOrder);
        } catch {
            browser.localStorage.removeItem(this.keyColumnOrder);
            return [];
        }
    },

    saveColumnOrder() {
        if (!this.columnOrder.length) {
            browser.localStorage.removeItem(this.keyColumnOrder);
            return;
        }
        browser.localStorage.setItem(this.keyColumnOrder, JSON.stringify(this.columnOrder));
    },

    getNormalizedColumnOrder() {
        const currentOrder = this.allColumns.map(getColumnKey);
        const savedOrder = this.columnOrder.filter((columnId) => currentOrder.includes(columnId));
        return [...savedOrder, ...currentOrder.filter((columnId) => !savedOrder.includes(columnId))];
    },

    sortColumnsBySavedOrder(columns) {
        if (!this.columnOrder.length) {
            return columns;
        }
        const orderIndex = new Map(
            this.getNormalizedColumnOrder().map((columnId, index) => [columnId, index])
        );
        return [...columns].sort((left, right) => {
            const leftIndex = orderIndex.get(getColumnKey(left)) ?? Number.MAX_SAFE_INTEGER;
            const rightIndex = orderIndex.get(getColumnKey(right)) ?? Number.MAX_SAFE_INTEGER;
            return leftIndex - rightIndex;
        });
    },

    onColumnReorderDrop(element, previous, next) {
        const movedId = element?.dataset?.columnId;
        if (!movedId) {
            return;
        }

        const order = this.getNormalizedColumnOrder().filter((columnId) => columnId !== movedId);
        const previousId = previous?.dataset?.columnId;
        const nextId = next?.dataset?.columnId;

        let targetIndex = order.length;
        if (nextId) {
            targetIndex = order.indexOf(nextId);
        } else if (previousId) {
            targetIndex = order.indexOf(previousId) + 1;
        }

        if (targetIndex < 0) {
            targetIndex = order.length;
        }

        order.splice(targetIndex, 0, movedId);
        this.columnOrder = order;
        this.saveColumnOrder();
        this.preventReorder = true;
        this.render();
    },
});

