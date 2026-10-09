/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useFileUploader } from "@web/core/utils/files";
import { _t } from "@web/core/l10n/translation";

const MAX_MEDIA_COUNT = 20;
const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const MAX_VIDEO_SIZE = 100 * 1024 * 1024;

function getMediaError(file, currentCount) {
    if (currentCount >= MAX_MEDIA_COUNT) {
        return _t("A record can contain at most 20 media files.");
    }
    if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) {
        return _t("Only image and video files can be uploaded.");
    }
    const limit = file.type.startsWith("video/") ? MAX_VIDEO_SIZE : MAX_IMAGE_SIZE;
    return file.size > limit ? _t("This file exceeds the allowed size limit.") : "";
}

const DRAFT_STORAGE_KEY = "wd_qooling_inbound_pda_draft_id";
const DRAFT_FIELDS = [
    "name", "state", "location_id", "date", "warehouse_operator_id", "supervisor_id", "ref_no", "mrn_number",
    "seal_number", "skal_bio_product", "bl_number", "bl_required", "container_shipment_number", "goods_status", "unloading_permission",
    "checked_visible_damage", "checked_received_quantity", "checked_product_quality",
    "packaging_condition", "gas_measurement", "adr", "un_number",
    "temperature_measured", "pallet_temperature_registered",
    "average_temperature_per_pallet", "amount_of_pallets", "amount_of_cartons", "comments", "warehouse_signature",
];

export class QoolingInboundPda extends Component {
    static template = "wd_qooling_app.InboundPda";
    static props = { "*": true };

    setup() {
        this.setValue = this.setValue.bind(this);
        this.deletePhoto = this.deletePhoto.bind(this);
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.uploadFiles = useFileUploader();
        this.signatureCanvas = useRef("signatureCanvas");
        const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString();
        this.state = useState({
            record: { date: localNow.slice(0, 10), filing_date: localNow.slice(0, 10), adr: "no" },
            warehouses: [],
            users: [],
            recordId: null,
            readOnly: false,
            photos: [],
            busy: false,
            error: "",
            saved: "",
            preview: false,
        });
        onWillStart(async () => {
            [this.state.warehouses, this.state.users] = await Promise.all([
                this.orm.searchRead("stock.warehouse", [], ["name"], { limit: 100 }),
                this.orm.searchRead("res.users", [["share", "=", false]], ["name"], { limit: 100 }),
            ]);
            await this.loadDraft();
        });
        onMounted(() => this.setupSignature());
        onWillUnmount(() => this.teardownSignature());
    }

    get isReadOnly() {
        return this.state.readOnly;
    }

    async loadDraft() {
        if (this.props.action?.context?.new_record) {
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            return;
        }
        const contextDraftId = this.props.action?.context?.active_id;
        const storedDraftId = Number(sessionStorage.getItem(DRAFT_STORAGE_KEY) || 0);
        const draftId = Number(contextDraftId || storedDraftId);
        if (!draftId) {
            return;
        }
        const [record] = await this.orm.read("wd.qooling.inbound.form", [draftId], DRAFT_FIELDS);
        if (!record || !["draft", "submitted"].includes(record.state)) {
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            return;
        }
        for (const field of ["location_id", "warehouse_operator_id", "supervisor_id"]) {
            record[field] = record[field]?.[0] || false;
        }
        this.state.recordId = record.id;
        this.state.readOnly = record.state !== "draft";
        Object.assign(this.state.record, record);
        await this.loadPhotos();
    }

    async refreshRecordName() {
        if (!this.state.recordId) return;
        const [record] = await this.orm.read("wd.qooling.inbound.form", [this.state.recordId], ["name"]);
        this.state.record.name = record?.name || "New";
    }

    setValue(name, value) {
        if (this.isReadOnly) return;
        this.state.record[name] = value;
        this.state.error = "";
    }

    onFieldChange(event) {
        const field = event.target.dataset.field;
        let value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
        if (["location_id", "warehouse_operator_id", "supervisor_id"].includes(field)) {
            value = Number(value);
        } else if (["average_temperature_per_pallet", "amount_of_pallets", "amount_of_cartons"].includes(field)) {
            value = Number(value);
        }
        if (field === "bl_required" && value !== "required") this.state.record.bl_number = "";
        this.setValue(field, value);
    }

    validateRequiredFields() {
        const requiredFields = [
            ["location_id", "Location"],
            ["date", "Date"],
            ["supervisor_id", "Supervisor"],
            ["goods_status", "Goods status"],
            ["unloading_permission", "Unloading permission"],
            ["adr", "ADR"],
        ];
        const missingField = requiredFields.find(([field]) => !this.state.record[field]);
        if (missingField) {
            this.state.error = _t("Complete all required fields before saving.");
            return false;
        }
        if (this.state.record.bl_required === "required" && !this.state.record.bl_number) {
            this.state.error = _t("B/L number is required when B/L is required.");
            return false;
        }
        return true;
    }

    async save() {
        if (this.isReadOnly) return;
        this.state.saved = "";
        if (!this.validateRequiredFields()) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const values = { ...this.state.record };
        delete values.state;
        try {
            if (this.state.recordId) {
                await this.orm.write("wd.qooling.inbound.form", [this.state.recordId], values);
            } else {
                const [recordId] = await this.orm.create("wd.qooling.inbound.form", [values]);
                this.state.recordId = recordId;
                await this.refreshRecordName();
            }
            this.state.record.state = "draft";
            sessionStorage.setItem(DRAFT_STORAGE_KEY, String(this.state.recordId));
            await this.loadPhotos();
            this.state.saved = _t("Draft saved");
            this.notification.add(_t("Inbound draft saved."), { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not save the draft.");
        } finally {
            this.state.busy = false;
        }
    }

    async submit() {
        if (this.isReadOnly) return;
        this.state.saved = "";
        if (!this.validateRequiredFields()) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        const values = { ...this.state.record };
        delete values.state;
        try {
            if (!this.state.recordId) {
                const [recordId] = await this.orm.create("wd.qooling.inbound.form", [values]);
                this.state.recordId = recordId;
                await this.refreshRecordName();
            } else {
                await this.orm.write("wd.qooling.inbound.form", [this.state.recordId], values);
            }
            await this.orm.call("wd.qooling.inbound.form", "action_submit", [[this.state.recordId]]);
            this.state.record.state = "submitted";
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            this.state.saved = _t("Submitted");
            this.notification.add(_t("Inbound record submitted."), { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not submit the record.");
        } finally {
            this.state.busy = false;
        }
    }

    openWebForm() {
        return this.action.doAction("wd_qooling_app.action_qooling_inbound_form", {
            additionalContext: this.state.recordId ? { active_id: this.state.recordId } : {},
        });
    }

    async onPhoto(event) {
        if (this.state.busy) return;
        if (!event.target.files.length) { event.target.value = ""; return; }
        this.state.saved = "";
        if (!this.state.recordId) {
            await this.save();
            if (!this.state.recordId) { event.target.value = ""; return; }
            this.state.saved = "";
        }
        if (this.state.record.state !== "draft") {
            this.state.error = _t("Media evidence can only be changed while the record is a draft.");
            event.target.value = "";
            return;
        }
        let currentCount = this.state.photos.length;
        const files = [];
        for (const file of event.target.files) {
            const mediaError = getMediaError(file, currentCount);
            if (mediaError) {
                this.state.error = mediaError;
                continue;
            }
            currentCount += 1;
            files.push(file);
        }
        event.target.value = "";
        if (!files.length) return;
        this.state.busy = true;
        try {
            const uploadedFiles = await this.uploadFiles("/web/binary/upload_attachment", {
                csrf_token: odoo.csrf_token, ufile: files, model: "wd.qooling.inbound.form", id: this.state.recordId,
            });
            const uploadError = uploadedFiles?.find((file) => file.error)?.error;
            if (uploadError) throw new Error(uploadError);
            const photoIds = uploadedFiles?.map((file) => file.id).filter(Boolean) || [];
            if (!photoIds.length) throw new Error(_t("Could not upload the media."));
            await this.orm.write("wd.qooling.inbound.form", [this.state.recordId], { photo_ids: photoIds.map((id) => [4, id]) });
            await this.loadPhotos();
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not upload the media.");
        } finally {
            this.state.busy = false;
        }
    }

    isVideo(photo) {
        return photo?.mimetype?.startsWith("video/");
    }

    getPreviewPhoto() {
        return this.state.photos.find((photo) => photo.id === this.state.preview);
    }

    async loadPhotos() {
        if (!this.state.recordId) {
            this.state.photos = [];
            return;
        }
        const [record] = await this.orm.read("wd.qooling.inbound.form", [this.state.recordId], ["photo_ids"]);
        this.state.photos = record?.photo_ids.length
            ? await this.orm.read("ir.attachment", record.photo_ids, ["name", "mimetype"])
            : [];
    }

    async deletePhoto(photoId) {
        if (this.isReadOnly) return;
        if (!this.state.recordId) {
            return;
        }
        try {
            await this.orm.write("wd.qooling.inbound.form", [this.state.recordId], {
                photo_ids: [[3, photoId]],
            });
            await this.orm.unlink("ir.attachment", [photoId]);
            await this.loadPhotos();
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not delete the photo.");
        }
    }

    setupSignature() {
        const canvas = this.signatureCanvas.el;
        if (!canvas) {
            return;
        }
        this.signatureElement = canvas;
        canvas.width = canvas.clientWidth || 500;
        canvas.height = 160;
        this.signatureContext = canvas.getContext("2d");
        this.signatureContext.lineWidth = 2;
        this.signatureContext.lineCap = "round";
        this.drawing = false;
        this.restoreSignature(canvas);
        this.signatureStart = (event) => {
            this.drawing = true;
            canvas.setPointerCapture?.(event.pointerId);
            const rect = canvas.getBoundingClientRect();
            this.signatureContext.beginPath();
            this.signatureContext.moveTo(event.clientX - rect.left, event.clientY - rect.top);
        };
        this.signatureMove = (event) => {
            if (!this.drawing) return;
            const rect = canvas.getBoundingClientRect();
            this.signatureContext.lineTo(event.clientX - rect.left, event.clientY - rect.top);
            this.signatureContext.stroke();
            this.signatureContext.beginPath();
            this.signatureContext.moveTo(event.clientX - rect.left, event.clientY - rect.top);
        };
        this.signatureEnd = () => {
            if (!this.drawing) return;
            this.drawing = false;
            this.setValue("warehouse_signature", canvas.toDataURL("image/png").split(",")[1]);
        };
        canvas.addEventListener("pointerdown", this.signatureStart);
        canvas.addEventListener("pointermove", this.signatureMove);
        canvas.addEventListener("pointerup", this.signatureEnd);
        canvas.addEventListener("pointercancel", this.signatureEnd);
    }

    restoreSignature(canvas) {
        const signature = this.state.record.warehouse_signature;
        if (!signature) {
            return;
        }
        const image = new Image();
        image.onload = () => {
            if (this.signatureElement === canvas) {
                this.signatureContext.drawImage(image, 0, 0, canvas.width, canvas.height);
            }
        };
        image.src = `data:image/png;base64,${signature}`;
    }

    clearSignature() {
        if (this.signatureContext && this.signatureCanvas.el) {
            this.signatureContext.clearRect(0, 0, this.signatureCanvas.el.width, this.signatureCanvas.el.height);
        }
        this.setValue("warehouse_signature", false);
    }

    teardownSignature() {
        const canvas = this.signatureElement;
        if (!canvas || !this.signatureStart) return;
        canvas.removeEventListener("pointerdown", this.signatureStart);
        canvas.removeEventListener("pointermove", this.signatureMove);
        canvas.removeEventListener("pointerup", this.signatureEnd);
        canvas.removeEventListener("pointercancel", this.signatureEnd);
        this.signatureElement = null;
        this.signatureContext = null;
    }
}

registry.category("actions").add("wd_qooling_inbound_pda", QoolingInboundPda);
