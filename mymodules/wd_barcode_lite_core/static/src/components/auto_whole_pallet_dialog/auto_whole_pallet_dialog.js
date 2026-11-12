/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class AutoWholePalletDialog extends Component {
    static template = "stock_barcode_lite.AutoWholePalletDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        palletName: String,
        lines: Array,
        onConfirm: Function,
        onCancel: Function,
    };

    setup() {
        this.state = useState({ confirming: false });
    }

    async confirm() {
        if (this.state.confirming) return;
        this.state.confirming = true;
        try {
            await this.props.onConfirm();
        } finally {
            this.state.confirming = false;
            this.props.close();
        }
    }

    cancel() {
        if (this.state.confirming) return;
        this.props.onCancel();
        this.props.close();
    }
}
