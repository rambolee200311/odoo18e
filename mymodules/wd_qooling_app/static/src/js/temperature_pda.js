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
    { key: "temperatures", label: _t("Pallet temperatures") },
    { key: "checks", label: _t("Checks") },
    { key: "evidence", label: _t("Evidence") },
    { key: "signature", label: _t("Signature") },
];
const CHECKS = [
    ["packaging_damage", _t("Packaging visible damage")],
    ["unpacked_housing_damage", _t("Unpackaged housing damage")],
    ["electrolyte_leakage", _t("Electrolyte leakage")],
    ["storage_stability", _t("Storage stability")],
];
const DRAFT_STORAGE_KEY = "wd_qooling_temperature_pda_draft_id";
const RECORD_FIELDS = [
    "name", "state", "date", "manager_id", "customer", "container_number", "location_id",
    "filing_date", "packaging_damage", "unpacked_housing_damage", "electrolyte_leakage",
    "storage_stability", "comments", "signature",
];

export class QoolingTemperaturePda extends Component {
    static template = "wd_qooling_app.TemperaturePda";
    static props = { "*": true };

    setup() {
        this.startSignature = this.startSignature.bind(this);
        this.moveSignature = this.moveSignature.bind(this);
        this.endSignature = this.endSignature.bind(this);
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.canvas = useRef("signatureCanvas");
        this.state = useState({
            record: { date: new Date().toISOString().slice(0, 16), filing_date: new Date().toISOString().slice(0, 10) },
            warehouses: [], users: [], recordId: null, readOnly: false, lines: [], photos: [], step: 0,
            busy: false, error: "", saved: "", preview: false, quickTemperature: "",
        });
        onWillStart(async () => {
            [this.state.warehouses, this.state.users] = await Promise.all([
                this.orm.searchRead("stock.warehouse", [], ["name"], { limit: 100 }),
                this.orm.searchRead("res.users", [["share", "=", false]], ["name"], { limit: 100 }),
            ]);
            await this.loadDraft();
        });
        onPatched(() => {
            if (this.state.step === 4 && this.canvas.el && !this.signatureContext) this.setupCanvas();
            if (this.state.step !== 4) this.teardownCanvas();
        });
        onWillUnmount(() => this.teardownCanvas());
    }

    get steps() { return STEPS; }

    get checks() { return CHECKS; }

    get isReadOnly() { return this.state.readOnly; }

    async loadDraft() {
        if (this.props.action?.context?.new_record) {
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            return;
        }
        const contextId = this.props.action?.context?.active_id;
        const storedId = Number(sessionStorage.getItem(DRAFT_STORAGE_KEY) || 0);
        const id = Number(contextId || storedId);
        if (!id) return;
        const [record] = await this.orm.read("wd.qooling.temperature.record", [id], RECORD_FIELDS);
        if (!record || !["draft", "submitted"].includes(record.state)) {
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            return;
        }
        for (const field of ["manager_id", "location_id"]) record[field] = record[field]?.[0] || false;
        record.date = record.date?.replace(" ", "T").slice(0, 16);
        this.state.recordId = record.id;
        this.state.readOnly = record.state !== "draft";
        Object.assign(this.state.record, record);
        await Promise.all([this.loadLines(), this.loadPhotos()]);
    }

    async refreshRecordName() {
        if (!this.state.recordId) return;
        const [record] = await this.orm.read("wd.qooling.temperature.record", [this.state.recordId], ["name"]);
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
        if (["manager_id", "location_id"].includes(field)) value = Number(value);
        if (event.target.type === "datetime-local") value = value.replace("T", " ");
        this.setValue(field, value);
    }

    validateRequired() {
        const fields = [["date", "Date"], ["manager_id", "Manager"], ["customer", "Customer"], ["container_number", "Container number"]];
        const missing = fields.find(([name]) => !this.state.record[name]);
        if (missing) { this.state.error = `${missing[1]} is required before saving.`; return false; }
        return true;
    }

    async persist() {
        if (this.isReadOnly) return;
        const values = { ...this.state.record };
        if (values.date) values.date = values.date.replace("T", " ");
        if (this.state.recordId) await this.orm.write("wd.qooling.temperature.record", [this.state.recordId], values);
        else {
            [this.state.recordId] = await this.orm.create("wd.qooling.temperature.record", [values]);
            await this.refreshRecordName();
        }
        this.state.record.state = "draft";
        sessionStorage.setItem(DRAFT_STORAGE_KEY, String(this.state.recordId));
        await Promise.all([this.loadLines(), this.loadPhotos()]);
    }

    async save() {
        if (this.isReadOnly) return;
        if (!this.validateRequired()) return;
        this.state.busy = true; this.state.error = "";
        try {
            await this.persist();
            this.state.saved = "Draft saved";
            this.notification.add("Temperature draft saved.", { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not save the draft.";
        } finally { this.state.busy = false; }
    }

    async submit() {
        if (this.isReadOnly) return;
        if (!this.validateRequired()) return;
        if (!this.state.record.signature) { this.state.error = "Signature is required before submission."; return; }
        this.state.busy = true; this.state.error = "";
        try {
            await this.persist();
            await this.orm.call("wd.qooling.temperature.record", "action_submit", [[this.state.recordId]]);
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            this.state.record.state = "submitted";
            this.state.saved = "Submitted";
            this.notification.add("Temperature record submitted.", { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not submit the record.";
        } finally { this.state.busy = false; }
    }

    previous() { this.state.step = Math.max(0, this.state.step - 1); }
    next() { this.state.step = Math.min(STEPS.length - 1, this.state.step + 1); }
    openWebForm() {
        return this.action.doAction("wd_qooling_app.action_qooling_temperature_record", {
            additionalContext: this.state.recordId ? { active_id: this.state.recordId } : {},
        });
    }

    async loadLines() {
        if (!this.state.recordId) return;
        this.state.lines = await this.orm.searchRead("wd.qooling.temperature.record.line",
            [["record_id", "=", this.state.recordId]], ["pallet_number", "temperature"], { order: "sequence,id" });
    }

    async addTemperature(event) {
        if (this.isReadOnly) return;
        if (event) event.preventDefault();
        const value = Number(this.state.quickTemperature);
        if (!Number.isFinite(value)) { this.state.error = "Enter a valid temperature."; return; }
        try {
            if (!this.state.recordId) {
                if (!this.validateRequired()) return;
                await this.persist();
            }
            await this.orm.write("wd.qooling.temperature.record", [this.state.recordId], {
                quick_temperature: value,
            });
            await this.orm.call("wd.qooling.temperature.record", "action_add_quick_temperature", [[this.state.recordId]]);
            this.state.quickTemperature = "";
            await this.loadLines();
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not add the temperature.";
        }
    }

    async updateLine(line, event) {
        try {
            await this.orm.write("wd.qooling.temperature.record.line", [line.id], {
                temperature: Number(event.target.value),
            });
            await this.loadLines();
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not update the temperature.";
        }
    }

    async clearAll() {
        if (this.isReadOnly) return;
        if (!this.state.recordId || !confirm("Clear all pallet temperatures?")) return;
        try {
            await this.orm.call("wd.qooling.temperature.record", "action_clear_lines", [[this.state.recordId]]);
            await this.loadLines();
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not clear pallet temperatures.";
        }
    }

    onPhoto(event) {
        if (!this.state.recordId) { this.state.error = "Save the draft before uploading media."; event.target.value = ""; return; }
        if (this.state.record.state !== "draft") {
            this.state.error = "Media evidence can only be changed while the record is a draft.";
            event.target.value = ""; return;
        }
        let currentCount = this.state.photos.length;
        for (const file of event.target.files) {
            const mediaError = getMediaError(file, currentCount);
            if (mediaError) { this.state.error = mediaError; continue; }
            currentCount += 1;
            const reader = new FileReader();
            reader.onload = async () => {
                try {
                    const [attachmentId] = await this.orm.create("ir.attachment", [{
                        name: file.name, datas: reader.result.split(",")[1], mimetype: file.type,
                        res_model: "wd.qooling.temperature.record", res_id: this.state.recordId,
                    }]);
                    await this.orm.write("wd.qooling.temperature.record", [this.state.recordId], { photo_ids: [[4, attachmentId]] });
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
        if (!this.state.recordId) { this.state.photos = []; return; }
        this.state.photos = await this.orm.searchRead("ir.attachment", [
            ["res_model", "=", "wd.qooling.temperature.record"], ["res_id", "=", this.state.recordId],
            ["res_field", "=", false],
        ], ["name", "mimetype"]);
    }

    async deletePhoto(id) {
        if (this.isReadOnly) return;
        try {
            await this.orm.write("wd.qooling.temperature.record", [this.state.recordId], { photo_ids: [[3, id]] });
            await this.orm.unlink("ir.attachment", [id]);
            await this.loadPhotos();
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not delete the photo.";
        }
    }

    setupCanvas() {
        const canvas = this.canvas.el;
        canvas.width = canvas.clientWidth || 500; canvas.height = 160;
        this.signatureContext = canvas.getContext("2d");
        this.signatureContext.lineWidth = 2; this.signatureContext.lineCap = "round";
        const signature = this.state.record.signature;
        if (signature) {
            const image = new Image();
            image.onload = () => this.signatureContext?.drawImage(image, 0, 0, canvas.width, canvas.height);
            image.src = `data:image/png;base64,${signature}`;
        }
    }

    startSignature(event) {
        const canvas = event.currentTarget;
        if (!this.signatureContext) this.setupCanvas();
        const point = event.touches?.[0] || event;
        const rect = canvas.getBoundingClientRect();
        this.drawing = true;
        this.signatureContext.beginPath();
        this.signatureContext.moveTo(point.clientX - rect.left, point.clientY - rect.top);
        event.preventDefault?.();
    }

    moveSignature(event) {
        if (!this.drawing || !this.signatureContext) return;
        const point = event.touches?.[0] || event;
        const rect = this.canvas.el.getBoundingClientRect();
        this.signatureContext.lineTo(point.clientX - rect.left, point.clientY - rect.top);
        this.signatureContext.stroke();
        this.signatureContext.beginPath();
        this.signatureContext.moveTo(point.clientX - rect.left, point.clientY - rect.top);
        event.preventDefault?.();
    }

    endSignature(event) {
        if (!this.drawing) return;
        this.drawing = false;
        this.setValue("signature", this.canvas.el.toDataURL("image/png").split(",")[1]);
        event.preventDefault?.();
    }

    clearSignature() {
        if (this.signatureContext && this.canvas.el) this.signatureContext.clearRect(0, 0, this.canvas.el.width, this.canvas.el.height);
        this.setValue("signature", false);
    }

    teardownCanvas() { this.signatureContext = null; this.drawing = false; }
}

registry.category("actions").add("wd_qooling_temperature_pda", QoolingTemperaturePda);
