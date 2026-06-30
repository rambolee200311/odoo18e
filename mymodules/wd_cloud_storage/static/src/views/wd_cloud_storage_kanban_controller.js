/** @odoo-module **/

import {registry} from "@web/core/registry";
import {kanbanView} from "@web/views/kanban/kanban_view";
import {KanbanController} from "@web/views/kanban/kanban_controller";
import {useService} from "@web/core/utils/hooks";
import {_t} from "@web/core/l10n/translation";
import {useRef, useState, onWillStart, onPatched} from "@odoo/owl";
import {WdCloudStorageKanbanRenderer} from "./wd_cloud_storage_kanban_renderer";

export class WdCloudStorageKanbanController extends KanbanController {
    static template = "wd_cloud_storage.WdCloudStorageKanbanView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.upload_input_ref = useRef("uploadInput");
        this.last_node_id = false;
        this.state = useState({can_upload: false, can_create_folder: false, selected_count: 0, selected_state: false});
        this.selected_record = false;
        this.preview_state = useState({preview_store: {}});

        onWillStart(async () => {
            await this.refresh_action_visibility();
        });

        onPatched(() => {
            this.refresh_action_visibility();
        });
    }

    build_viewer_file(payload) {
        const mimetype = payload.mimetype || "";
        const is_image = mimetype.startsWith("image/");
        const is_pdf = mimetype === "application/pdf";
        const is_text = mimetype.startsWith("text/");
        const is_video = mimetype.startsWith("video/");
        const default_source = is_pdf
            ? `/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent(payload.preview_url)}#pagemode=none`
            : payload.preview_url;

        return {
            displayName: payload.display_name,
            downloadUrl: payload.download_url,
            defaultSource: default_source,
            mimetype: mimetype,
            isViewable: !!payload.is_viewable,
            isImage: is_image,
            isPdf: is_pdf,
            isText: is_text,
            isVideo: is_video,
        };
    }

    async openRecord(record, mode) {
        this.select_record(record);

        const payload = await this.orm.call("s3.stored.file", "get_file_viewer_payload", [record.resId]);
        const file = this.build_viewer_file(payload);

        if (file.isViewable) {
            this.preview_state.preview_store = {
                files: [file],
                startIndex: 0,
                close: () => this.close_preview(),
            };
            return;
        }

        window.open(payload.download_url, "_self");
    }

    close_preview() {
        this.preview_state.preview_store = {};
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

    select_record(record) {
        const selected_records = this.model.root.selection || [];
        for (const selected_record of selected_records) {
            if (selected_record !== record && selected_record.toggleSelection) {
                selected_record.toggleSelection(false);
            }
        }
        if (record && record.toggleSelection && !record.selected) {
            record.toggleSelection(true);
        }
        this.selected_record = record;
        this.state.selected_count = record ? 1 : 0;
        this.state.selected_state = record && record.data ? record.data.state : false;
    }

    clear_selected_record() {
        const selected_records = this.model.root.selection || [];
        for (const selected_record of selected_records) {
            if (selected_record.toggleSelection) {
                selected_record.toggleSelection(false);
            }
        }
        this.selected_record = false;
        this.state.selected_count = 0;
        this.state.selected_state = false;
        this.preview_state.preview_store = {};
    }

    async on_click_restore_selected() {
        const record_ids = this.get_selected_record_ids();
        if (!record_ids.length) {
            return;
        }
        try {
            await this.orm.call("s3.stored.file", "action_restore_from_recycle", [record_ids]);
            this.clear_selected_record();
            await this.model.load();
        } catch (error) {
            this.notify_error(error, _t("Restore failed."));
        }
    }

    onUnselectAll() {
        this.clear_selected_record();
    }

    get_selected_record_ids() {
        if (this.selected_record && this.selected_record.resId) {
            return [this.selected_record.resId];
        }
        return (this.model.root.selection || []).map((record) => record.resId).filter((id) => !!id);
    }

    async on_click_move_selected_to_recycle() {
        const record_ids = this.get_selected_record_ids();
        if (!record_ids.length) {
            return;
        }
        try {
            await this.orm.call("s3.stored.file", "action_move_to_recycle_bin", [record_ids]);
            this.clear_selected_record();
            await this.model.load();
        } catch (error) {
            this.notify_error(error, _t("Move to recycle failed."));
        }
    }

    async on_click_rename_selected() {
        const record_ids = this.get_selected_record_ids();
        if (record_ids.length !== 1) {
            this.notification.add(_t("Please select one file to rename."), {type: "warning"});
            return;
        }

        try {
            await this.action.doAction("wd_cloud_storage.action_s3_rename_file_wizard", {
                additionalContext: {default_file_id: record_ids[0]},
                onClose: async () => {
                    this.preview_state.preview_store = {};
                    await this.model.load();
                },
            });
        } catch (error) {
            this.notify_error(error, _t("Rename failed."));
        }
    }

    on_click_download_selected() {
        const record_ids = this.get_selected_record_ids();
        if (record_ids.length !== 1) {
            this.notification.add(_t("Please select one file to download."), {type: "warning"});
            return;
        }
        window.open(`/wd_cloud_storage/content/${record_ids[0]}?download=1`, "_self");
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

export const wd_cloud_storage_kanban_view = {
    ...kanbanView,
    Controller: WdCloudStorageKanbanController,
    Renderer: WdCloudStorageKanbanRenderer,
};

registry.category("views").add("wd_cloud_storage_kanban", wd_cloud_storage_kanban_view);
