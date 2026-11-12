/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class VasPdaOrderList extends Component {
    static props = { ...standardActionServiceProps };
    static template = "wd_warehouse_value_add.VasPdaOrderList";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({ busy: false, orders: [] });
        onWillStart(() => this.loadOrders());
    }

    async loadOrders() {
        this.state.busy = true;
        try {
            this.state.orders = await this.orm.searchRead("wd.vas.order", [], ["name", "state", "source_type", "source_document_number", "project_id"], { order: "id desc" });
        } finally {
            this.state.busy = false;
        }
    }

    openOrder(order) {
        return this.action.doAction({ type: "ir.actions.client", tag: "wd_warehouse_value_add.pda", context: { ...this.props.action.context, vas_order_id: order.id } });
    }

    goBack() {
        window.history.back();
    }
}

registry.category("actions").add("wd_warehouse_value_add.pda_order_list", VasPdaOrderList);
