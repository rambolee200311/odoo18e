/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

class BondedBarcodeHomepage extends Component {
    static template = "wd_bonded_wms.BondedBarcodeHomepage";
    static props = { ...standardActionServiceProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this._creatingInternalTransfer = false;
    }

    _onInboundClick() {
        this.action.doAction("wd_bonded_wms.action_bonded_barcode_inbound_scan");
    }

    _onOutboundWholeClick() {
        this.action.doAction("wd_bonded_wms.action_bonded_barcode_outbound_whole");
    }

    _onOutboundBreakClick() {
        this.action.doAction("wd_bonded_wms.action_bonded_barcode_outbound_break");
    }

    async _onInternalTransferClick() {
        if (this._creatingInternalTransfer) {
            return;
        }
        this._creatingInternalTransfer = true;
        try {
            const result = await this.orm.call("stock.picking", "action_create_bonded_pda_internal_transfer", []);
            if (result?.type === "ir.actions.client") {
                result.context = { ...(result.context || {}), barcode_home_action: "wd_bonded_wms.action_bonded_barcode_homepage" };
                await this.action.doAction(result);
            }
        } catch (error) {
            this.notification.add(error?.message || "Could not create an internal transfer.", { type: "danger" });
        } finally {
            this._creatingInternalTransfer = false;
        }
    }
}

registry.category("actions").add("wd_bonded_wms_barcode_homepage", BondedBarcodeHomepage);
