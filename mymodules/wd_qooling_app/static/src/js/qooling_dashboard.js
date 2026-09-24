/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class QoolingDashboard extends Component {
    static template = "wd_qooling_app.QoolingDashboard";

    setup() {
        this.action = useService("action");
    }

    openWebForm(xmlId) {
        return this.action.doAction(xmlId);
    }
}

registry.category("actions").add("qooling_dashboard", QoolingDashboard);
