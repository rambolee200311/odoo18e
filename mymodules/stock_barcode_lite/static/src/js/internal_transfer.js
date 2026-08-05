/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class InternalTransferPage extends Component {
    static template = "stock_barcode_lite.InternalTransferPage";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            step: "new",        // new | scan_location | scan_package | done
            picking_id: null,
            location_dest_id: null,
            location_dest_name: "",
            scanned_packages: [],
            is_validating: false,
        });
    }

    async _onNewTransfer() {
        this.state.step = "new";
        this.state.scanned_packages = [];
        this.state.location_dest_id = null;
        this.state.location_dest_name = "";

        try {
            const result = await this.orm.call("stock.picking", "action_pda_create_internal_transfer", []);
            if (result) {
                this.state.picking_id = result.id;
                this.state.step = "scan_location";
            }
        } catch (error) {
            this.notification.add("Failed to create transfer: " + error.message, { type: "danger" });
        }
    }

    async _onScanLocation(barcode) {
        try {
            const result = await this.orm.call("stock.picking", "action_pda_scan_location", [
                this.state.picking_id, barcode
            ]);
            if (result.success) {
                this.state.location_dest_id = result.location_id;
                this.state.location_dest_name = result.location_name;
                this.state.step = "scan_package";
            } else {
                this.notification.add(result.message, { type: "warning" });
            }
        } catch (error) {
            this.notification.add("Scan location failed: " + error.message, { type: "danger" });
        }
    }

    async _onScanPackage(barcode) {
        try {
            const result = await this.orm.call("stock.picking", "action_pda_scan_package", [
                this.state.picking_id, barcode
            ]);
            if (result.success) {
                this.state.scanned_packages.push(result.package);
            } else {
                this.notification.add(result.message, { type: "warning" });
            }
        } catch (error) {
            this.notification.add("Scan package failed: " + error.message, { type: "danger" });
        }
    }

    async _onValidate() {
        if (this.state.scanned_packages.length === 0) {
            this.notification.add("Please scan at least one package", { type: "warning" });
            return;
        }

        this.state.is_validating = true;
        try {
            const result = await this.orm.call("stock.picking", "action_pda_validate_transfer", [
                this.state.picking_id
            ]);
            if (result.success) {
                this.state.step = "done";
                this.notification.add("Transfer completed successfully!", { type: "success" });
            } else {
                this.notification.add(result.message, { type: "danger" });
            }
        } catch (error) {
            this.notification.add("Validation failed: " + error.message, { type: "danger" });
        } finally {
            this.state.is_validating = false;
        }
    }

    _onRemovePackage(packageId) {
        this.state.scanned_packages = this.state.scanned_packages.filter(
            p => p.id !== packageId
        );
    }

    _onClearDestination() {
        this.state.location_dest_id = null;
        this.state.location_dest_name = "";
        this.state.step = "scan_location";
    }

    _onBackToHome() {
        this.action.doAction("stock_barcode_lite_homepage");
    }
}