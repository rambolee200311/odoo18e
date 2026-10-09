/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
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

const CHECKS = [
    ["loading_plan_discussed", _t("Loading plan discussed")],
    ["adr_separation_compatibility", _t("ADR separation / compatibility")],
    ["weight_distribution", _t("Weight distribution checked")],
    ["check_loading_visible_damage", _t("Loading: visible damage")],
    ["check_loading_quantity", _t("Loading: quantity checked")],
    ["cargo_packaging", _t("Cargo packaging")],
    ["cargo_identification", _t("Cargo identification")],
    ["cargo_secured", _t("Cargo secured")],
    ["vehicle_adr_certificate", _t("Vehicle ADR certificate")],
    ["vehicle_fire_extinguisher", _t("Vehicle fire extinguisher")],
    ["vehicle_adr_sign", _t("Vehicle ADR sign")],
    ["vehicle_fixing_material", _t("Vehicle fixing material")],
    ["vehicle_trem_card", _t("Vehicle TREM card")],
    ["driver_adr_certificate", _t("Driver ADR certificate")],
    ["driver_safety_vest", _t("Driver safety vest")],
    ["driver_eye_protection", _t("Driver eye protection")],
    ["driver_protective_gloves", _t("Driver protective gloves")],
    ["driver_wheel_chock", _t("Driver wheel chock")],
    ["driver_tarpaulin", _t("Driver tarpaulin")],
    ["driver_flashlight", _t("Driver flashlight")],
    ["driver_shovel", _t("Driver shovel")],
    ["driver_drip_tray", _t("Driver drip tray")],
    ["driver_eyewash", _t("Driver eyewash")],
    ["driver_warning_triangles", _t("Driver warning triangles")],
];
const DRAFT_STORAGE_KEY = "wd_qooling_outbound_pda_draft_id";
const DRAFT_FIELDS = [
    "name", "state", "location_id", "date_arrival", "start_loading_at", "end_loading_at",
    "supervisor_id", "ref_no", "goods_type", "mrn_number", "seal_number",
    "mrn_checked_before_release", "adr", "un_number", "proper_shipping_name",
    "measured_temperature", "loading_plan_discussed", "adr_separation_compatibility",
    "weight_distribution", "check_loading_visible_damage", "check_loading_quantity",
    "cargo_packaging", "cargo_identification", "cargo_secured",
    "vehicle_adr_certificate", "vehicle_fire_extinguisher", "vehicle_adr_sign",
    "vehicle_fixing_material", "vehicle_trem_card", "driver_adr_certificate",
    "driver_safety_vest", "driver_eye_protection", "driver_protective_gloves",
    "driver_wheel_chock", "driver_tarpaulin", "driver_flashlight", "driver_shovel",
    "driver_drip_tray", "driver_eyewash", "driver_warning_triangles",
    "driver_comments", "driver_signature", "warehouse_operator_comments",
    "warehouse_signature", "filing_date",
];

export class QoolingOutboundPda extends Component {
    static template = "wd_qooling_app.OutboundPda";
    static props = { "*": true };

    setup() {
        this.startSignature = this.startSignature.bind(this);
        this.moveSignature = this.moveSignature.bind(this);
        this.endSignature = this.endSignature.bind(this);
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.uploadFiles = useFileUploader();
        this.canvasRefs = {
            driver: useRef("driverSignatureCanvas"),
            warehouse: useRef("warehouseSignatureCanvas"),
        };
        const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString();
        this.state = useState({
            record: {
                date_arrival: localNow.slice(0, 16), start_loading_at: localNow.slice(0, 16),
                end_loading_at: localNow.slice(0, 16), filing_date: localNow.slice(0, 10),
                goods_type: "bonded",
                adr: "no",
            },
            warehouses: [], users: [], recordId: null, readOnly: false, photos: [],
            busy: false, error: "", saved: "", preview: false,
        });
        onWillStart(async () => {
            [this.state.warehouses, this.state.users] = await Promise.all([
                this.orm.searchRead("stock.warehouse", [], ["name"], { limit: 100 }),
                this.orm.searchRead("res.users", [["share", "=", false]], ["name"], { limit: 100 }),
            ]);
            await this.loadDraft();
        });
        onMounted(() => {
            this.setupSignature("driver");
            this.setupSignature("warehouse");
        });
    }

    get checks() { return CHECKS; }

    get isReadOnly() { return this.state.readOnly; }

    async loadDraft() {
        if (this.props.action?.context?.new_record) {
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            return;
        }
        const contextDraftId = this.props.action?.context?.active_id;
        const storedDraftId = Number(sessionStorage.getItem(DRAFT_STORAGE_KEY) || 0);
        const draftId = Number(contextDraftId || storedDraftId);
        if (!draftId) return;
        const [record] = await this.orm.read("wd.qooling.outbound.form", [draftId], DRAFT_FIELDS);
        if (!record || !["draft", "submitted", "exception_pending", "closed"].includes(record.state)) {
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            return;
        }
        for (const field of ["location_id", "supervisor_id"]) record[field] = record[field]?.[0] || false;
        for (const field of ["date_arrival", "start_loading_at", "end_loading_at"]) {
            if (!record[field]) continue;
            const datetime = new Date(`${record[field].replace(" ", "T")}Z`);
            record[field] = new Date(datetime.getTime() - datetime.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        }
        this.state.recordId = record.id;
        this.state.readOnly = record.state !== "draft";
        Object.assign(this.state.record, record);
        await this.loadPhotos();
    }

    async refreshRecordName() {
        if (!this.state.recordId) return;
        const [record] = await this.orm.read("wd.qooling.outbound.form", [this.state.recordId], ["name"]);
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
        if (["location_id", "supervisor_id"].includes(field)) value = Number(value);
        this.setValue(field, value);
    }

    validateRequiredFields() {
        const required = [
            ["location_id", "Location"], ["date_arrival", "Arrival time"],
            ["start_loading_at", "Start loading time"], ["end_loading_at", "End loading time"],
            ["supervisor_id", "Supervisor"], ["goods_type", "Goods type"], ["adr", "ADR"],
        ];
        const missing = required.find(([field]) => !this.state.record[field]);
        if (missing) { this.state.error = _t("Complete all required fields before saving."); return false; }
        return true;
    }

    async persist() {
        if (this.isReadOnly) return;
        const values = { ...this.state.record };
        delete values.state;
        for (const field of ["date_arrival", "start_loading_at", "end_loading_at"]) {
            if (values[field]) values[field] = new Date(values[field]).toISOString().slice(0, 19).replace("T", " ");
        }
        if (this.state.recordId) {
            await this.orm.write("wd.qooling.outbound.form", [this.state.recordId], values);
        } else {
            const [recordId] = await this.orm.create("wd.qooling.outbound.form", [values]);
            this.state.recordId = recordId;
            await this.refreshRecordName();
        }
        this.state.record.state = "draft";
        sessionStorage.setItem(DRAFT_STORAGE_KEY, String(this.state.recordId));
        await this.loadPhotos();
    }

    async save() {
        if (this.isReadOnly) return;
        this.state.saved = "";
        if (!this.validateRequiredFields()) return;
        this.state.busy = true; this.state.error = "";
        try {
            await this.persist();
            this.state.saved = _t("Draft saved");
            this.notification.add(_t("Outbound draft saved."), { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not save the draft.");
        } finally { this.state.busy = false; }
    }

    async submit() {
        if (this.isReadOnly) return;
        this.state.saved = "";
        if (!this.validateRequiredFields()) return;
        this.state.busy = true; this.state.error = "";
        try {
            await this.persist();
            await this.orm.call("wd.qooling.outbound.form", "action_submit", [[this.state.recordId]]);
            this.state.record.state = "submitted";
            sessionStorage.removeItem(DRAFT_STORAGE_KEY);
            this.state.saved = _t("Submitted");
            this.notification.add(_t("Outbound record submitted."), { type: "success" });
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not submit the record.");
        } finally { this.state.busy = false; }
    }

    openWebForm() {
        return this.action.doAction("wd_qooling_app.action_qooling_outbound_form", {
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
            event.target.value = ""; return;
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
                csrf_token: odoo.csrf_token, ufile: files, model: "wd.qooling.outbound.form", id: this.state.recordId,
            });
            const uploadError = uploadedFiles?.find((file) => file.error)?.error;
            if (uploadError) throw new Error(uploadError);
            const photoIds = uploadedFiles?.map((file) => file.id).filter(Boolean) || [];
            if (!photoIds.length) throw new Error(_t("Could not upload the media."));
            await this.orm.write("wd.qooling.outbound.form", [this.state.recordId], { photo_ids: photoIds.map((id) => [4, id]) });
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
        if (!this.state.recordId) { this.state.photos = []; return; }
        const [record] = await this.orm.read("wd.qooling.outbound.form", [this.state.recordId], ["photo_ids"]);
        this.state.photos = record?.photo_ids.length
            ? await this.orm.read("ir.attachment", record.photo_ids, ["name", "mimetype"])
            : [];
    }

    async deletePhoto(photoId) {
        if (this.isReadOnly) return;
        try {
            await this.orm.write("wd.qooling.outbound.form", [this.state.recordId], { photo_ids: [[3, photoId]] });
            await this.orm.unlink("ir.attachment", [photoId]);
            await this.loadPhotos();
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not delete the photo.");
        }
    }

    setupSignature(key) {
        const canvas = this.canvasRefs[key].el;
        if (!canvas) return;
        canvas.width = canvas.clientWidth || 500; canvas.height = 160;
        const context = canvas.getContext("2d");
        context.lineWidth = 2; context.lineCap = "round";
        this.restoreSignature(canvas, key);
    }

    startSignature(event, key) {
        const canvas = event.currentTarget;
        if (!canvas.width || !canvas.height) {
            canvas.width = canvas.clientWidth || 500;
            canvas.height = 160;
        }
        this.signatureKey = key;
        this.signatureElement = canvas;
        this.signatureContext = canvas.getContext("2d");
        this.signatureContext.lineWidth = 2;
        this.signatureContext.lineCap = "round";
        this.drawing = true;
        const point = event.touches?.[0] || event;
        const rect = canvas.getBoundingClientRect();
        this.signatureContext.beginPath();
        this.signatureContext.moveTo(point.clientX - rect.left, point.clientY - rect.top);
        event.preventDefault?.();
    }

    moveSignature(event) {
        if (!this.drawing || !this.signatureContext || !this.signatureElement) return;
        const point = event.touches?.[0] || event;
        const rect = this.signatureElement.getBoundingClientRect();
        this.signatureContext.lineTo(point.clientX - rect.left, point.clientY - rect.top);
        this.signatureContext.stroke();
        this.signatureContext.beginPath();
        this.signatureContext.moveTo(point.clientX - rect.left, point.clientY - rect.top);
        event.preventDefault?.();
    }

    endSignature(event) {
        if (!this.drawing || !this.signatureElement || !this.signatureKey) return;
        this.drawing = false;
        this.setValue(`${this.signatureKey}_signature`, this.signatureElement.toDataURL("image/png").split(",")[1]);
        event.preventDefault?.();
    }

    restoreSignature(canvas, key) {
        const signature = this.state.record[`${key}_signature`];
        if (!signature) return;
        const image = new Image();
        image.onload = () => canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
        image.src = `data:image/png;base64,${signature}`;
    }

    clearSignature(key) {
        const canvas = this.canvasRefs[key].el;
        if (canvas) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
        this.setValue(`${key}_signature`, false);
    }
}

registry.category("actions").add("wd_qooling_outbound_pda", QoolingOutboundPda);
