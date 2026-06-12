/** @odoo-module **/

import {Component} from "@odoo/owl";
import {FileViewer} from "@web/core/file_viewer/file_viewer";

export class WdCloudStorageFileViewer extends Component {
    static template = "wd_cloud_storage.FileViewer";
    static components = {FileViewer};
    static props = ["previewStore"];
}