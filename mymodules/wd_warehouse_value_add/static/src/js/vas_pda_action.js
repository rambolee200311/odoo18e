/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const WAREHOUSE_MODELS = {
    inbound: "world.depot.inbound.order",
    outbound: "world.depot.outbound.order",
    transfer: "world.depot.transfer.order",
};

export class VasPdaAction extends Component {
    static props = { ...standardActionServiceProps };
    static template = "wd_warehouse_value_add.VasPdaAction";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.user = user;
        this.state = useState({
            order: null,
            orderType: "inbound",
            billno: "",
            warehouseOrder: null,
            operationTypes: [],
            lines: [],
            quantityTime: 1,
            selectedOperationType: "",
            attachmentName: "",
            attachments: [],
            lineModalOpen: false,
            cancelModalOpen: false,
            cancelReason: "",
            lineDraft: {
                operationTypeId: "",
                quantityTime: 1,
                note: "",
            },
            busy: false,
        });
        onWillStart(async () => {
            this.state.operationTypes = await this.orm.searchRead(
                "wd.vas.operation.type",
                [["active", "=", true]],
                ["id", "name", "unit_id"],
                { order: "sequence, name" }
            );
        });
    }

    get isDraft() {
        return !this.state.order || this.state.order.state === "draft";
    }

    get statusLabel() {
        return {
            draft: "草稿",
            submitted: "已提交",
            cancelled: "已作废",
        }[this.state.order?.state] || "新建";
    }

    async resolveWarehouseOrder() {
        const billno = this.state.billno.trim();
        if (!billno) {
            this.state.warehouseOrder = null;
            return;
        }
        const records = await this.orm.searchRead(
            WAREHOUSE_MODELS[this.state.orderType],
            [["billno", "=", billno]],
            ["billno", "owner", "warehouse"],
            { limit: 1 }
        );
        this.state.warehouseOrder = records[0] || null;
        if (!this.state.warehouseOrder) {
            this.notification.add("Warehouse Order was not found.", { type: "warning" });
        }
    }

    async createDraft() {
        const billno = this.state.billno.trim();
        if (billno) {
            await this.resolveWarehouseOrder();
            if (!this.state.warehouseOrder) {
                return false;
            }
        }
        const values = {
            order_type: this.state.orderType,
            operator_id: user.userId,
        };
        if (this.state.warehouseOrder) {
            const [warehouseId] = this.state.warehouseOrder.warehouse || [];
            values.warehouse_order_billno = billno;
            values.warehouse_id = warehouseId;
        }
        const [orderId] = await this.orm.create("wd.vas.order", [values]);
        await this.reloadOrder(orderId);
        return true;
    }

    async reloadOrder(orderId = this.state.order?.id) {
        if (!orderId) {
            return;
        }
        const [order] = await this.orm.read(
            "wd.vas.order",
            [orderId],
            ["name", "create_date", "state", "operator_id", "warehouse_order_billno", "warehouse_id",
                "inbound_order_id", "outbound_order_id", "transfer_order_id", "attachment_ids"]
        );
        this.state.order = order;
        this.state.billno = order.warehouse_order_billno || this.state.billno;
        this.state.lines = await this.orm.searchRead(
            "wd.vas.order.line",
            [["order_id", "=", order.id]],
            ["id", "operation_type_id", "quantity_time", "unit_id", "note"],
            { order: "sequence, id" }
        );
        this.state.attachments = this.state.order.attachment_ids?.length
            ? await this.orm.read("ir.attachment", this.state.order.attachment_ids, ["id", "name"])
            : [];
    }

    openLineModal() {
        if (!this.isDraft) {
            return;
        }
        this.state.lineDraft = {
            operationTypeId: this.state.selectedOperationType || "",
            quantityTime: this.state.quantityTime || 1,
            note: "",
        };
        this.state.lineModalOpen = true;
    }

    closeLineModal() {
        this.state.lineModalOpen = false;
    }

    async confirmAddLine() {
        const { operationTypeId, quantityTime, note } = this.state.lineDraft;
        if (!operationTypeId) {
            this.notification.add("请选择作业类型。", { type: "warning" });
            return;
        }
        if (!this.state.order) {
            const created = await this.createDraft();
            if (!created) {
                this.notification.add("请先输入并解析关联单据号。", { type: "warning" });
                return;
            }
        }
        if (!this.state.order || !this.isDraft) {
            return;
        }
        await this.orm.create("wd.vas.order.line", [{
            order_id: this.state.order.id,
            operation_type_id: Number(operationTypeId),
            quantity_time: Number(quantityTime),
            note,
        }]);
        this.state.lineModalOpen = false;
        await this.reloadOrder();
    }

    async removeLine(lineId) {
        if (!this.isDraft) {
            return;
        }
        await this.orm.unlink("wd.vas.order.line", [lineId]);
        await this.reloadOrder();
    }

    async updateLine(line) {
        if (!this.isDraft) {
            return;
        }
        try {
            await this.orm.write("wd.vas.order.line", [line.id], {
                operation_type_id: Number(line.operation_type_id[0]),
                quantity_time: Number(line.quantity_time),
                note: line.note || "",
            });
            await this.reloadOrder();
            this.notification.add("Line updated.", { type: "success" });
        } catch (error) {
            this.notification.add(error.message || "Line update failed.", { type: "danger" });
            await this.reloadOrder();
        }
    }

    async saveDraft() {
        if (!this.state.order || !this.isDraft) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.write("wd.vas.order", [this.state.order.id], {
                warehouse_order_billno: this.state.billno.trim(),
            });
            await this.reloadOrder();
            this.notification.add("Draft saved.", { type: "success" });
        } finally {
            this.state.busy = false;
        }
    }

    async submit() {
        if (!this.state.order || !this.isDraft || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("wd.vas.order", "action_submit", [[this.state.order.id]]);
            await this.reloadOrder();
            this.notification.add("Submitted.", { type: "success" });
        } catch (error) {
            await this.reloadOrder();
            this.notification.add(
                this.state.order?.state === "submitted"
                    ? "The order was submitted. State was refreshed from the server."
                    : (error.message || "Submit failed."),
                { type: this.state.order?.state === "submitted" ? "success" : "danger" }
            );
        } finally {
            this.state.busy = false;
        }
    }

    async onFileChange(event) {
        const files = [...event.target.files];
        if (!files.length || !this.state.order || !this.isDraft) {
            return;
        }
        for (const file of files) {
            try {
                const data = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
                    reader.onerror = reject;
                    reader.readAsDataURL(file);
                });
                const [attachmentId] = await this.orm.create("ir.attachment", [{
                    name: file.name,
                    type: "binary",
                    datas: data,
                    res_model: "wd.vas.order",
                    res_id: this.state.order.id,
                }]);
                await this.orm.write("wd.vas.order", [this.state.order.id], {
                    attachment_ids: [[4, attachmentId]],
                });
                this.state.attachmentName = file.name;
            } catch (error) {
                this.notification.add(
                    `${file.name}: ${error.message || "Upload failed."}`,
                    { type: "danger" }
                );
            }
        }
        await this.reloadOrder();
    }

    async removeAttachment(attachmentId) {
        if (!this.isDraft) {
            return;
        }
        try {
            await this.orm.unlink("ir.attachment", [attachmentId]);
            await this.reloadOrder();
        } catch (error) {
            this.notification.add(error.message || "Attachment deletion failed.", { type: "danger" });
        }
    }

    newOrder() {
        this.state.order = null;
        this.state.warehouseOrder = null;
        this.state.billno = "";
        this.state.lines = [];
        this.state.attachments = [];
        this.state.attachmentName = "";
        this.state.cancelModalOpen = false;
        this.state.cancelReason = "";
    }

    openCancelModal() {
        if (this.state.order?.state !== "draft") {
            return;
        }
        this.state.cancelReason = "";
        this.state.cancelModalOpen = true;
    }

    closeCancelModal() {
        this.state.cancelModalOpen = false;
    }

    async confirmCancel() {
        const reason = this.state.cancelReason.trim();
        if (!reason || !this.state.order || this.state.order.state !== "draft") {
            this.notification.add("请输入作废原因。", { type: "warning" });
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("wd.vas.order", "action_cancel", [[this.state.order.id], reason]);
            this.state.cancelModalOpen = false;
            await this.reloadOrder();
            this.notification.add("作业单已作废。", { type: "success" });
        } catch (error) {
            this.notification.add(error.message || "作废失败。", { type: "danger" });
            await this.reloadOrder();
        } finally {
            this.state.busy = false;
        }
    }

    goBack() {
        window.history.back();
    }
}

registry.category("actions").add("wd_warehouse_value_add.pda", VasPdaAction);
