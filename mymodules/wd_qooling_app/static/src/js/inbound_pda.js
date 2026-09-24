/** @odoo-module **/

import { Component, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MAX_MEDIA_COUNT = 20;
const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const MAX_VIDEO_SIZE = 100 * 1024 * 1024;

function getMediaError(file, currentCount) {
    if (currentCount >= MAX_MEDIA_COUNT) {
        return `A record can contain at most ${MAX_MEDIA_COUNT} media files.`;
    }
    if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) {
        return _t("Only image and video files can be uploaded.");
    }
    const limit = file.type.startsWith("video/") ? MAX_VIDEO_SIZE : MAX_IMAGE_SIZE;
    return file.size > limit ? `This file exceeds the ${limit / (1024 * 1024)} MB limit.` : "";
}

const STEPS = [
    { key: "details", label: _t("Details") },
    { key: "checks", label: _t("Checks") },
    { key: "adr", label: _t("ADR & temperature") },
    { key: "evidence", label: _t("Evidence") },
    { key: "signature", label: _t("Signature") },
];
const DRAFT_STORAGE_KEY = "wd_qooling_inbound_pda_draft_id";
const DRAFT_FIELDS = [
    "name", "state", "location_id", "date", "supervisor_id", "ref_no",
    "container_shipment_number", "goods_status", "unloading_permission",
    "checked_visible_damage", "checked_received_quantity", "checked_product_quality",
    "packaging_condition", "gas_measurement", "adr", "un_number",
    "temperature_measured", "pallet_temperature_registered",
    "average_temperature_per_pallet", "comments", "warehouse_signature",
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
        this.signatureCanvas = useRef("signatureCanvas");
        this.state = useState({
            record: { date: new Date().toISOString().slice(0, 10), filing_date: new Date().toISOString().slice(0, 10), adr: "no" },
            warehouses: [],
            users: [],
            recordId: null,
            readOnly: false,
            photos: [],
            step: 0,
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
        onPatched(() => {
            if (this.state.step === 4 && this.signatureCanvas.el !== this.signatureElement) {
                this.teardownSignature();
                this.setupSignature();
            }
        });
        onWillUnmount(() => this.teardownSignature());
    }

    get steps() {
        return STEPS;
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
        for (const field of ["location_id", "supervisor_id"]) {
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
        if (["location_id", "supervisor_id"].includes(field)) {
            value = Number(value);
        } else if (field === "average_temperature_per_pallet") {
            value = Number(value);
        }
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
            this.state.error = `${missingField[1]} is required before saving.`;
            return false;
        }
        return true;
    }

    async save() {
        if (this.isReadOnly) return;
        if (!this.validateRequiredFields()) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            if (this.state.recordId) {
                await this.orm.write("wd.qooling.inbound.form", [this.state.recordId], this.state.record);
            } else {
                const [recordId] = await this.orm.create("wd.qooling.inbound.form", [this.state.record]);
                this.state.recordId = recordId;
                await this.refreshRecordName();
            }
            this.state.record.state = "draft";
            sessionStorage.setItem(DRAFT_STORAGE_KEY, String(this.state.recordId));
            await this.loadPhotos();
            this.state.saved = "Draft saved";
            this.notification.add("Inbound draft saved.", { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not save the draft.";
        } finally {
            this.state.busy = false;
        }
    }

    async submit() {
        if (this.isReadOnly) return;
        if (!this.validateRequiredFields()) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            if (!this.state.recordId) {
                const [recordId] = await this.orm.create("wd.qooling.inbound.form", [this.state.record]);
                this.state.recordId = recordId;
                await this.refreshRecordName();
            } else {
                await this.orm.write("wd.qooling.inbound.form", [this.state.recordId], this.state.record);
            }
            await this.orm.call("wd.qooling.inbound.form", "action_submit", [[this.state.recordId]]);
            this.state.record.state = "submitted";
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            this.state.saved = "Submitted";
            this.notification.add("Inbound record submitted.", { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not submit the record.";
        } finally {
            this.state.busy = false;
        }
    }

    previous() {
        this.state.step = Math.max(0, this.state.step - 1);
    }

    next() {
        this.state.step = Math.min(STEPS.length - 1, this.state.step + 1);
    }

    openWebForm() {
        return this.action.doAction("wd_qooling_app.action_qooling_inbound_form", {
            additionalContext: this.state.recordId ? { active_id: this.state.recordId } : {},
        });
    }

    onPhoto(event) {
        if (!this.state.recordId) {
            this.state.error = "Save the draft before uploading media.";
            event.target.value = "";
            return;
        }
        if (this.state.record.state !== "draft") {
            this.state.error = "Media evidence can only be changed while the record is a draft.";
            event.target.value = "";
            return;
        }
        let currentCount = this.state.photos.length;
        for (const file of event.target.files) {
            const mediaError = getMediaError(file, currentCount);
            if (mediaError) {
                this.state.error = mediaError;
                continue;
            }
            currentCount += 1;
            const reader = new FileReader();
            reader.onload = async () => {
                try {
                    const [attachmentId] = await this.orm.create("ir.attachment", [{
                        name: file.name,
                        datas: reader.result.split(",")[1],
                        mimetype: file.type,
                        res_model: "wd.qooling.inbound.form",
                        res_id: this.state.recordId,
                    }]);
                    await this.orm.write("wd.qooling.inbound.form", [this.state.recordId], {
                        photo_ids: [[4, attachmentId]],
                    });
                    await this.loadPhotos();
                } catch (error) {
                    this.state.error = error.data?.message || error.message || "Could not upload the media.";
                }
            };
            reader.readAsDataURL(file);
        }
        event.target.value = "";
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
        const records = await this.orm.searchRead(
            "ir.attachment",
            [
                ["res_model", "=", "wd.qooling.inbound.form"],
                ["res_id", "=", this.state.recordId],
                ["res_field", "=", false],
            ],
            ["name", "mimetype"],
        );
        this.state.photos = records;
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
            this.state.error = error.data?.message || error.message || "Could not delete the photo.";
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
