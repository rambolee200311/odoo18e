/** @odoo-module **/

import { Component, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class QoolingTemperatureQuickEntry extends Component {
    static template = "wd_qooling_app.QoolingTemperatureQuickEntry";
    static props = { ...standardFieldProps };

    setup() {
        this.input = useRef("input");
        this.submitting = false;
    }

    async onKeydown(event) {
        if (event.key !== "Enter" || this.submitting) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        const value = Number(event.target.value);
        if (!Number.isFinite(value)) {
            return;
        }
        this.submitting = true;
        try {
            await this.props.record.update({ [this.props.name]: value });
            const button = this.input.el?.closest(".o_form_sheet")
                ?.querySelector("button[name='action_add_quick_temperature']");
            button?.click();
            this.input.el?.focus();
        } finally {
            this.submitting = false;
        }
    }
}

registry.category("fields").add("qooling_temperature_quick_entry", {
    component: QoolingTemperatureQuickEntry,
    supportedTypes: ["float"],
});
