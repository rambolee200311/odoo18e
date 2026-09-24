/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class QoolingSignatureField extends Component {
    static template = "wd_qooling_app.QoolingSignatureField";
    static props = { ...standardFieldProps };

    setup() {
        this.canvas = useRef("canvas");
        onMounted(() => {
            this._setupCanvas();
            this._restoreSignature();
        });
        onWillUnmount(() => this._removeListeners());
    }

    _restoreSignature() {
        const recordId = this.props.record.resId;
        const model = this.props.record.resModel;
        if (!recordId || !model || !this.props.record.data[this.props.name]) {
            return;
        }
        const image = new Image();
        image.onload = () => {
            if (this.context && this.canvas.el) {
                this.context.drawImage(
                    image, 0, 0, this.canvas.el.width, this.canvas.el.height
                );
            }
        };
        image.src = `/web/image/${model}/${recordId}/${this.props.name}`;
    }

    _setupCanvas() {
        const canvas = this.canvas.el;
        canvas.width = canvas.clientWidth || 500;
        canvas.height = 180;
        this.context = canvas.getContext("2d");
        this.context.lineWidth = 2;
        this.context.lineCap = "round";
        this._drawing = false;
        this._start = (event) => {
            this._drawing = true;
            this.canvas.el.setPointerCapture?.(event.pointerId);
            const rect = this.canvas.el.getBoundingClientRect();
            this.context.beginPath();
            this.context.moveTo(event.clientX - rect.left, event.clientY - rect.top);
        };
        this._move = (event) => {
            if (this._drawing) {
                this._draw(event);
            }
        };
        this._end = () => {
            if (!this._drawing) {
                return;
            }
            this._drawing = false;
            this.context.beginPath();
            this.props.record.update({ [this.props.name]: canvas.toDataURL("image/png").split(",")[1] });
        };
        canvas.addEventListener("pointerdown", this._start);
        canvas.addEventListener("pointermove", this._move);
        canvas.addEventListener("pointerup", this._end);
        canvas.addEventListener("pointercancel", this._end);
        canvas.addEventListener("pointerleave", this._end);
        canvas.addEventListener("lostpointercapture", this._end);
    }

    _draw(event) {
        const rect = this.canvas.el.getBoundingClientRect();
        this.context.lineTo(event.clientX - rect.left, event.clientY - rect.top);
        this.context.stroke();
        this.context.beginPath();
        this.context.moveTo(event.clientX - rect.left, event.clientY - rect.top);
    }

    clear() {
        this.context.clearRect(0, 0, this.canvas.el.width, this.canvas.el.height);
        this.props.record.update({ [this.props.name]: false });
    }

    _removeListeners() {
        if (this.canvas.el && this._start) {
            this.canvas.el.removeEventListener("pointerdown", this._start);
            this.canvas.el.removeEventListener("pointermove", this._move);
            this.canvas.el.removeEventListener("pointerup", this._end);
            this.canvas.el.removeEventListener("pointercancel", this._end);
            this.canvas.el.removeEventListener("pointerleave", this._end);
            this.canvas.el.removeEventListener("lostpointercapture", this._end);
        }
    }
}

registry.category("fields").add("qooling_signature", {
    component: QoolingSignatureField,
    supportedTypes: ["binary"],
});
