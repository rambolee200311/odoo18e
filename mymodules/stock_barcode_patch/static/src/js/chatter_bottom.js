/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";

patch(FormRenderer.prototype, {
    mailLayout() {
        return this.mailStore ? "BOTTOM_CHATTER" : "NONE";
    },
});