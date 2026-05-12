/** @odoo-module **/

import {registry} from "@web/core/registry";
import {listView} from "@web/views/list/list_view";
import {ListController} from "@web/views/list/list_controller";
import {useService} from "@web/core/utils/hooks";
import {_t} from "@web/core/l10n/translation";
import {useRef, useState, onWillStart, onPatched} from "@odoo/owl";

export class WdCloudStorageListController extends ListController {
    static template = "wd_cloud_storage.WdCloudStorageListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.upload_input_ref = useRef("uploadInput");
        this.last_node_id = false;
        this.state = useState({can_upload: false, can_create_folder: false});

        onWillStart(async () => {
            await this.refresh_action_visibility();
        });

        onPatched(() => {
            this.refresh_action_visibility();
        });
    }

    get_search_model() {
        return this.env.searchModel || this.model.env.searchModel;
    }

    get_current_node_id() {
        const search_model = this.get_search_model();
        if (!search_model || !search_model.getSections) {
            return false;
        }
        const sections = search_model.getSections(
            (section) => section.type === "category" && section.fieldName === "node_id"
        );
        const active_value_id = sections.length ? sections[0].activeValueId : false;
        if (typeof active_value_id === "number") {
            return active_value_id;
        }
        if (typeof active_value_id === "string" && /^\d+$/.test(active_value_id)) {
            return Number(active_value_id);
        }
        return false;
    }

    async refresh_action_visibility() {
        const node_id = this.get_current_node_id();
        if (node_id === this.last_node_id) {
            return;
        }
        this.last_node_id = node_id;

        if (!node_id) {
            this.state.can_upload = false;
            this.state.can_create_folder = false;
            return;
        }

        let can_upload = false;
        let can_create_folder = false;

        try {
            await this.orm.call("s3.node", "check_can_upload_in_node", [node_id]);
            can_upload = true;
        } catch {
            can_upload = false;
        }

        try {
            await this.orm.call("s3.node", "check_can_create_subfolder_in_node", [node_id]);
            can_create_folder = true;
        } catch {
            can_create_folder = false;
        }

        this.state.can_upload = can_upload;
        this.state.can_create_folder = can_create_folder;
    }

    get show_new_menu() {
        return this.state.can_upload || this.state.can_create_folder;
    }

    get_odoo_error_message(error, fallback_message) {
        const data = error && typeof error === "object" && error.data && typeof error.data === "object"
            ? error.data
            : {};
        const args = Array.isArray(data["arguments"]) ? data["arguments"] : [];
        const args_msg = typeof args[0] === "string" ? args[0] : "";
        const data_msg = typeof data["message"] === "string" ? data["message"] : "";
        const err_msg = error && typeof error.message === "string" ? error.message : "";
        return args_msg || data_msg || err_msg || fallback_message || _t("Operation failed.");
    }

    notify_error(error, fallback_message) {
        this.notification.add(this.get_odoo_error_message(error, fallback_message), {
            type: "danger",
            sticky: true,
        });
    }

    async on_click_upload() {
        const node_id = this.get_current_node_id();
        if (!node_id) {
            this.notification.add(_t("Please select a folder on the left first."), {type: "warning"});
            return;
        }
        try {
            await this.orm.call("s3.node", "check_can_upload_in_node", [node_id]);
            this.upload_input_ref.el.value = "";
            this.upload_input_ref.el.click();
        } catch (error) {
            this.notify_error(error, _t("Uploads are not allowed in the current folder."));
        }
    }

    async on_upload_file_change(ev) {
        const node_id = this.get_current_node_id();
        const file = ev.target.files && ev.target.files.length ? ev.target.files[0] : false;
        if (!node_id || !file) {
            return;
        }
        try {
            await this.orm.call("s3.node", "check_can_upload_in_node", [node_id]);
            const base64_data = await this.file_to_base64(file);
            await this.orm.call("s3.stored.file", "create_from_upload", [node_id, base64_data, file.name]);
            await this.model.load();
        } catch (error) {
            this.notify_error(error, _t("Upload failed."));
        } finally {
            if (this.upload_input_ref.el) {
                this.upload_input_ref.el.value = "";
            }
        }
    }

    async on_click_create_folder() {
        const node_id = this.get_current_node_id();
        if (!node_id) {
            this.notification.add(_t("Please select a folder on the left first."), {type: "warning"});
            return;
        }
        try {
            await this.orm.call("s3.node", "check_can_create_subfolder_in_node", [node_id]);
            await this.action.doAction("wd_cloud_storage.action_s3_create_folder_wizard", {
                additionalContext: {default_node_id: node_id},
                onClose: async () => {
                    await this.action.doAction({type: "ir.actions.client", tag: "reload"});
                },
            });
        } catch (error) {
            this.notify_error(error, _t("Failed to create the folder."));
        }
    }


    file_to_base64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = String(reader.result || "");
                resolve(result.includes(",") ? result.split(",")[1] : result);
            };
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }
}

export const WdCloudStorageListView = {
    ...listView,
    Controller: WdCloudStorageListController,
};

registry.category("views").add("wd_cloud_storage_list", WdCloudStorageListView);
