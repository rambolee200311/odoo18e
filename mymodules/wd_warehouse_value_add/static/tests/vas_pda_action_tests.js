/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import { VasPdaAction } from "../src/js/vas_pda_action";

function makeAction(state = {}) {
    const action = Object.create(VasPdaAction.prototype);
    action.state = {
        order: null,
        orderType: "inbound",
        billno: "",
        warehouseOrder: null,
        lines: [],
        attachments: [],
        lineModalOpen: true,
        cancelModalOpen: false,
        cancelReason: "",
        lineDraft: {
            operationTypeId: "",
            quantityTime: 1,
            note: "",
        },
        busy: false,
        ...state,
    };
    action.notification = { add: () => {} };
    action.orm = {
        create: async () => [1],
        write: async () => {},
        unlink: async () => {},
        call: async () => {},
    };
    action.reloadOrder = async () => {};
    return action;
}

test("CC04 frontend test bundle loads", () => {
    expect(true).toBe(true);
});

test("PDA status labels follow the server state", () => {
    const action = makeAction();

    expect(action.statusLabel).toBe("新建");
    action.state.order = { state: "draft" };
    expect(action.statusLabel).toBe("草稿");
    action.state.order.state = "submitted";
    expect(action.statusLabel).toBe("已提交");
    action.state.order.state = "cancelled";
    expect(action.statusLabel).toBe("已作废");
});

test("PDA new order clears the current draft state", () => {
    const action = makeAction({
        order: { id: 7, state: "draft" },
        billno: "IO202609070001",
        warehouseOrder: { id: 9 },
        lines: [{ id: 3 }],
        attachments: [{ id: 4 }],
        attachmentName: "photo.jpg",
        cancelModalOpen: true,
        cancelReason: "duplicate",
    });

    action.newOrder();

    expect(action.state.order).toBe(null);
    expect(action.state.billno).toBe("");
    expect(action.state.warehouseOrder).toBe(null);
    expect(action.state.lines.length).toBe(0);
    expect(action.state.attachments.length).toBe(0);
    expect(action.state.attachmentName).toBe("");
    expect(action.state.cancelModalOpen).toBe(false);
    expect(action.state.cancelReason).toBe("");
});

test("PDA rejects a line without an operation type", async () => {
    const action = makeAction();
    const notifications = [];
    action.notification.add = (message, options) => notifications.push({ message, options });

    await action.confirmAddLine();

    expect(notifications.length).toBe(1);
    expect(notifications[0].message).toBe("请选择作业类型。");
});

test("PDA creates an unassociated draft before adding the first line", async () => {
    const action = makeAction({
        lineDraft: { operationTypeId: "12", quantityTime: 2, note: "贴标" },
    });
    const calls = [];
    action.orm.create = async (model, values) => {
        calls.push({ model, values });
        return model === "wd.vas.order" ? [7] : [8];
    };
    action.reloadOrder = async (orderId) => {
        if (orderId) {
            action.state.order = { id: orderId, state: "draft" };
        }
    };

    await action.confirmAddLine();

    expect(calls.length).toBe(2);
    expect(calls[0].model).toBe("wd.vas.order");
    expect(calls[0].values[0].order_type).toBe("inbound");
    expect(calls[1].model).toBe("wd.vas.order.line");
    expect(calls[1].values[0].order_id).toBe(7);
    expect(calls[1].values[0].operation_type_id).toBe(12);
    expect(calls[1].values[0].quantity_time).toBe(2);
    expect(calls[1].values[0].note).toBe("贴标");
    expect(action.state.lineModalOpen).toBe(false);
});

test("PDA requires a reason before cancelling a draft", async () => {
    const action = makeAction({
        order: { id: 7, state: "draft" },
    });
    const notifications = [];
    action.notification.add = (message, options) => notifications.push({ message, options });

    await action.confirmCancel();

    expect(notifications.length).toBe(1);
    expect(notifications[0].message).toBe("请输入作废原因。");
});
