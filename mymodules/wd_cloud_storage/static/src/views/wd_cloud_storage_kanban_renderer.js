/** @odoo-module **/

import {KanbanRenderer} from "@web/views/kanban/kanban_renderer";
import {WdCloudStorageFileViewer} from "./wd_cloud_storage_file_viewer";

export class WdCloudStorageKanbanRenderer extends KanbanRenderer {
    static template = "wd_cloud_storage.KanbanRenderer";
    static props = [...KanbanRenderer.props, "previewStore?"];
    static components = {
        ...KanbanRenderer.components,
        WdCloudStorageFileViewer,
    };
}