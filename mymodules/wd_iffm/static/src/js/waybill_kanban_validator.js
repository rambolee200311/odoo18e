/** @odoo-module */

import { KanbanRenderer } from '@web/views/kanban/kanban_renderer';
import { useService } from '@web/core/utils/hooks';

/**
 * 提单看板：跨泳道拖拽前置校验。
 * 根据目标泳道的 state，调用后端对应方法做 dry-run 校验：
 *   target = new      → action_unconfirm_order
 *   target = confirm  → action_confirm_order
 *   target = done     → action_done_order
 *   target = cancel   → action_cancel_order
 * 校验通过 → 放行走原生拖拽（web_save 更新 state）
 * 校验失败 → 弹通知，阻止原生拖拽
 *
 * Bug Fix:
 * - 问题1（状态错乱）：不再依赖 sortStart 时 props.list.groups 中的 records 快照
 *   （super.sortStart() 会触发 useSortable 移除 dragged record），改在 sortRecordDrop
 *   时通过 ORM 直接从数据库读取 record 当前真实 state，确保校验基于最新数据。
 * - 问题2（cancel 卡片消失）：通过 ORM 读取排除掉了数据不同步的可能。
 * - 问题3（datapoint vs resId）：dataRecordId 是 Odoo 内部的 datapoint ID（如 "datapoint_13"），
 *   不是数据库 ID。需要从 props.list.groups 中找到对应 record 的 resId。
 */
export class WaybillKanbanValidator extends KanbanRenderer {
    setup() {
        super.setup();
        this.orm = useService('orm');
        this.notification = useService('notification');
    }

    // ── 拖拽放置：前置校验 ────────────────────────────────────────
    async sortRecordDrop(dataRecordId, dataGroupId, { element, parent }) {
        // 1. 获取目标泳道的 state
        const targetGroupEl = parent || element?.closest('.o_kanban_group');
        const targetGroupId = targetGroupEl?.dataset?.id || dataGroupId;
        const targetState = this._getGroupStateById(targetGroupId);

        // 2. 从 groups 中找到 resId（数据库 ID）
        // dataRecordId 是 datapoint 内部 ID（如 "datapoint_13"），不是数据库 ID
        const groups = this.props.list?.groups || [];
        let recordDbId = null;
        for (const group of groups) {
            const records = group.records || [];
            for (const record of records) {
                if (String(record.id) === String(dataRecordId)) {
                    recordDbId = record.resId;
                    break;
                }
            }
            if (recordDbId) break;
        }

        if (!recordDbId || isNaN(parseInt(recordDbId, 10))) {
            await super.sortRecordDrop(...arguments);
            return;
        }

        const recordId = parseInt(recordDbId, 10);

        // 3. 通过 ORM 读取当前 state
        let sourceState = null;
        try {
            const records = await this.orm.read(
                'world.depot.waybill',
                [recordId],
                ['state']
            );
            sourceState = records[0]?.state ?? null;
        } catch (_) {
            // 读取失败 → 放行让原生处理
            await super.sortRecordDrop(...arguments);
            return;
        }

        // 4. 同组内排序 → 直接放行
        if (sourceState === targetState) {
            await super.sortRecordDrop(...arguments);
            return;
        }

        // 5. 跨状态拖拽 → 调用后端校验方法
        const methodMap = {
            new:     'action_unconfirm_order',
            confirm: 'action_confirm_order',
            done:    'action_done_order',
            cancel:  'action_cancel_order',
        };

        const method = methodMap[targetState];
        if (!method) {
            await super.sortRecordDrop(...arguments);
            return;
        }

        try {
            await this.orm.call(
                'world.depot.waybill',
                method,
                [[recordId]]
            );
        } catch (err) {
            const msg =
                err?.data?.arguments?.[0] ||
                (err?.data?.message
                    ? err.data.message.replace(/^odoo\.exceptions\.[^:]+:\s*/, '')
                    : '') ||
                err?.message ||
                'Validation failed';
            this.notification.add(msg, {
                type: 'danger',
                title: 'Cannot Move',
            });
            return; // 不调用 super → 原生拖拽被阻止
        }

        // 6. 校验通过 → 放行
        await super.sortRecordDrop(...arguments);
    }

    // ── 辅助方法 ───────────────────────────────────────────────

    /**
     * 通过 group datapoint id 获取该泳道的 state 值。
     */
    _getGroupStateById(groupId) {
        if (!groupId) {
            return null;
        }
        const groups = this.props.list?.groups || [];
        const found = groups.find(g => String(g.id) === String(groupId));
        return found?.value ?? null;
    }
}
