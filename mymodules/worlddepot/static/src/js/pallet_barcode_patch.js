/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

function waitForModelAndPatch() {
    const targetComponent = registry.category("actions").get("stock_barcode_client_action");
    if (targetComponent && targetComponent.prototype) {
        const originalSetup = targetComponent.prototype.setup;
        targetComponent.prototype.setup = function () {
            originalSetup.call(this);
            const originalPutInPack = this.env.model._putInPack;
            this.env.model._putInPack = async function () {
                try {
                    // Prompt the user to scan the pallet barcode
                    const barcode = await scanBarcode(this.env, {
                        title: _t("Pallet Scan"),
                        placeholder: _t("Please scan the pallet barcode"),
                    });

                    if (barcode) {
                        // Send the scanned barcode to the backend
                        await rpc({
                            route: "/stock_barcode/update_pallet",
                            params: { pallet_barcode: barcode, res_id: this.context.active_id },
                        });
                        this.notify(_t("Pallet barcode scanned successfully."), { type: "success" });
                    } else {
                        this.notification.add(_t("No barcode detected. Please try again."), { type: "warning" });
                    }
                } catch (error) {
                    this.notification.add(_t("Scan failed: ") + error.message, { type: "danger" });
                }
            };
        };
        console.log("Patch successfully applied to stock_barcode_client_action model.");
    } else {
        console.warn("stock_barcode_client_action not found. Retrying...");
        setTimeout(waitForModelAndPatch, 100); // Retry after 100ms
    }
}

// Ensure the patch is applied after the component is rendered
registry.category("actions").add("pallet_barcode_patch", {
    start() {
        waitForModelAndPatch();
    },
});