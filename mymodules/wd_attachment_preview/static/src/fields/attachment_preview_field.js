/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { FileModel } from "@web/core/file_viewer/file_model";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { FileInput } from "@web/core/file_input/file_input";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useX2ManyCrud } from "@web/views/fields/relational_utils";
import { Component } from "@odoo/owl";

export class AttachmentPreviewField extends Component {
    static template = "wd_attachment_preview.AttachmentPreviewField";
    static components = { FileInput };
    static props = {
        ...standardFieldProps,
        acceptedFileExtensions: { type: String, optional: true },
        className: { type: String, optional: true },
        numberOfFiles: { type: Number, optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.file_viewer = useFileViewer();
        this.operations = useX2ManyCrud(() => this.props.record.data[this.props.name], true);
    }

    get files() {
        return this.props.record.data[this.props.name].records.map((record) => Object.assign(new FileModel(), { ...record.data, id: record.resId }));
    }

    get media() {
        return this.files.filter((file) => file.isImage || file.isVideo);
    }

    get other_files() {
        return this.files.filter((file) => !file.isImage && !file.isVideo);
    }

    get upload_text() {
        return this.props.record.fields[this.props.name].string;
    }

    get_image_url(file) {
        return `/web/image/${file.id}/96x72`;
    }

    get_media_url(file) {
        return file.isVideo ? `/web/content/${file.id}` : this.get_image_url(file);
    }

    get_file_extension(file) {
        return file.name.includes(".") ? file.name.split(".").pop() : "";
    }

    on_preview(file) {
        const files = this.files;
        const target = files.find((item) => item.id === file.id);
        if (target && target.isViewable) {
            this.file_viewer.open(target, files);
        }
    }

    async on_file_uploaded(files) {
        for (const file of files) {
            if (file.error) {
                return this.notification.add(file.error, { title: _t("Uploading error"), type: "danger" });
            }
            await this.operations.saveRecord([file.id]);
        }
    }

    async on_file_remove(delete_id) {
        const record = this.props.record.data[this.props.name].records.find((item) => item.resId === delete_id);
        await this.orm.unlink("ir.attachment", [delete_id]);
        this.operations.removeRecord(record);
    }
}

export const attachment_preview_field = {
    component: AttachmentPreviewField,
    displayName: _t("Attachment Preview"),
    supportedOptions: [
        { label: _t("Accepted file extensions"), name: "accepted_file_extensions", type: "string" },
        { label: _t("Number of files"), name: "number_of_files", type: "integer" },
    ],
    supportedTypes: ["many2many"],
    isEmpty: () => false,
    relatedFields: [
        { name: "name", type: "char" },
        { name: "mimetype", type: "char" },
    ],
    extractProps: ({ attrs, options }) => ({
        acceptedFileExtensions: options.accepted_file_extensions,
        className: attrs.class,
        numberOfFiles: options.number_of_files,
    }),
};

registry.category("fields").add("attachment_preview", attachment_preview_field);
