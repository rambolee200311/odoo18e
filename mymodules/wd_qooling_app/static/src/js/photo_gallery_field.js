/** @odoo-module **/

import { Component, onPatched, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { FileInput } from "@web/core/file_input/file_input";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useX2ManyCrud } from "@web/views/fields/relational_utils";

export class QoolingPhotoGalleryField extends Component {
    static template = "wd_qooling_app.QoolingPhotoGalleryField";
    static components = { FileInput };
    static props = { ...standardFieldProps };

    setup() {
        this.onFileRemove = this.onFileRemove.bind(this);
        this.openPreview = this.openPreview.bind(this);
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.operations = useX2ManyCrud(() => this.props.record.data[this.props.name], true);
        this.state = useState({ previewId: null, metadata: {}, metadataKey: "" });
        onWillStart(() => this.loadMetadata());
        onPatched(() => this.loadMetadata());
    }

    get files() {
        return this.props.record.data[this.props.name].records.map((record) => ({
            id: record.resId,
            name: this.state.metadata[record.resId]?.name || record.data.name || "",
            mimetype: this.state.metadata[record.resId]?.mimetype || record.data.mimetype || "",
        }));
    }

    async loadMetadata() {
        const ids = this.props.record.data[this.props.name].records
            .map((record) => record.resId)
            .filter(Boolean);
        const key = ids.join(",");
        if (key === this.state.metadataKey) {
            return;
        }
        this.state.metadataKey = key;
        if (!ids.length) {
            this.state.metadata = {};
            return;
        }
        const records = await this.orm.searchRead(
            "ir.attachment",
            [["id", "in", ids]],
            ["name", "mimetype"],
        );
        for (const record of records) {
            this.state.metadata[record.id] = record;
        }
    }

    get canEdit() {
        return !this.props.record.data.state || this.props.record.data.state === "draft";
    }

    getUrl(id) {
        return `/web/content/${id}`;
    }

    async onFileUploaded(files) {
        for (const file of files) {
            if (file.error) {
                this.notification.add(file.error, { type: "danger" });
                continue;
            }
            try {
                await this.operations.saveRecord([file.id]);
            } catch (error) {
                this.notification.add(error.data?.message || error.message || "Could not upload the media.", {
                    type: "danger",
                });
                try {
                    await this.orm.unlink("ir.attachment", [file.id]);
                } catch (cleanupError) {
                    this.notification.add(
                        cleanupError.data?.message || cleanupError.message || "Could not clean up the rejected media.",
                        { type: "danger" },
                    );
                }
            }
        }
    }

    async onFileRemove(id) {
        const record = this.props.record.data[this.props.name].records.find(
            (candidate) => candidate.resId === id
        );
        if (record) {
            try {
                await this.operations.removeRecord(record);
            } catch (error) {
                this.notification.add(error.data?.message || error.message || "Could not delete the media.", {
                    type: "danger",
                });
            }
        }
    }

    get hasRecordId() {
        return Boolean(this.props.record.resId);
    }

    openPreview(id) {
        this.state.previewId = id;
    }

    getPreviewFile() {
        return this.files.find((file) => file.id === this.state.previewId);
    }

    isVideo(file) {
        return file?.mimetype?.startsWith("video/");
    }

    closePreview() {
        this.state.previewId = null;
    }
}

registry.category("fields").add("qooling_photo_gallery", {
    component: QoolingPhotoGalleryField,
    supportedTypes: ["many2many"],
});
