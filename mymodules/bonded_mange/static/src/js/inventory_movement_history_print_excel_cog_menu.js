/** @odoo-module **/

import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { STATIC_ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";

const cog_menu_registry = registry.category("cogMenu");

export class InventoryMovementHistoryPrintExcel extends Component {
    static template = "bonded_mange.InventoryMovementHistoryPrintExcel";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
    }

    async on_print_excel() {
        const report_id = this.env.searchModel.context.inventory_movement_history_report_id;
        if (!report_id) {
            return;
        }
        const action = await this.env.services.orm.call(
            "bonded.inventory.movement.history.report",
            "action_print_excel",
            [[report_id]]
        );
        await this.action.doAction(action);
    }
}

const inventory_movement_history_print_excel_item = {
    Component: InventoryMovementHistoryPrintExcel,
    groupNumber: STATIC_ACTIONS_GROUP_NUMBER,
    isDisplayed: (env) => (
        !env.isSmall &&
        env.config.actionType === "ir.actions.act_window" &&
        env.config.viewType === "list" &&
        env.searchModel.resModel === "bonded.inventory.movement.history.report.line" &&
        Boolean(env.searchModel.context.inventory_movement_history_report_id)
    ),
};

cog_menu_registry.add(
    "bonded-inventory-movement-history-print-excel",
    inventory_movement_history_print_excel_item,
    { sequence: 11 }
);
