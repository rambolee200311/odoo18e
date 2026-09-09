/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class VasDashboard extends Component {
    static props = { ...standardActionServiceProps };
    static template = "wd_warehouse_value_add.VasDashboard";

    setup() {
        this.action = useService("action");
    }

    openPda() {
        return this.action.doAction("wd_warehouse_value_add.action_vas_pda");
    }

    openOrders() {
        return this.action.doAction("wd_warehouse_value_add.action_vas_order");
    }
}

registry.category("actions").add("wd_warehouse_value_add.dashboard", VasDashboard);
