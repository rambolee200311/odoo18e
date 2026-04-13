/** @odoo-module */

import { registry } from '@web/core/registry';
import { kanbanView } from '@web/views/kanban/kanban_view';
import { KanbanRenderer } from '@web/views/kanban/kanban_renderer';
import { useService } from '@web/core/utils/hooks';
import { onMounted, onPatched } from "@odoo/owl";
import { WorkbenchKanbanRecord } from './workbench_kanban_record';

/**
 * 工作台看板：预报（waybill）卡片拖入「换单 / 清关」泳道触发业务 RPC；
 * 换单/清关之间的卡片走 Odoo 原生排序（同组内拖拽）。
 *
 * 配合 arch 属性 records_draggable="1" 使用。
 */
export class WorkbenchKanbanRenderer extends KanbanRenderer {
    static components = {
        ...KanbanRenderer.components,
        KanbanRecord: WorkbenchKanbanRecord,
    };

    setup() {
        super.setup();
        this.orm = useService('orm');
        this.notification = useService('notification');
        this.action = useService('action');
        this.isCreating = false;

        /** laneId → lane code 缓存（初始化时填充） */
        this._laneCodeCache = new Map();
        /** group datapoint id → laneId 映射 */
        this._groupIdToLaneId = new Map();

        // 拖拽时保存的信息（sortStart → sortRecordDrop 传递）
        this._dragInfo = {
            sourceRecordId: null,
            sourceGroupId: null,
            sourceLaneCode: null,
        };

        onMounted(() => {
            this._buildLaneCache();

//            console.log("【加载完成】看板数据：", this.props.list);
//            console.log("【分组列表】：", this.props.list.groups);
        });

        onPatched(() => {
            this._buildLaneCache();
        });
    }

    // ── 泳道缓存 ─────────────────────────────────────────────────────────────

    async _buildLaneCache() {
        // 获取分组列表
        const groups = this.props.list?.groups || [];
        const laneIds = [];
        groups.forEach((g) => {
            const laneId = g.value ?? null;
            if (laneId) {
                laneIds.push(laneId);
                // 缓存：group datapoint id → laneId
                this._groupIdToLaneId.set(String(g.id), laneId);
            }
        });
        if (laneIds.length === 0 || this._laneCodeCache.size > 0) {
            return;
        }
        try {
            const records = await this.orm.read(
                'operation.workbench.lane', laneIds, ['code']
            );
            records.forEach((r) => {
                this._laneCodeCache.set(r.id, r.code);
            });
        } catch (_) { /* 忽略错误 */ }
    }

    /**
     * 通过 group datapoint id（DOM dataset.id）获取泳道 code。
     */
    _getLaneCodeByGroupId(groupId) {
        const laneId = this._groupIdToLaneId.get(String(groupId));
        if (laneId && this._laneCodeCache.has(laneId)) {
            return this._laneCodeCache.get(laneId);
        }
        return null;
    }

    /**
     * 通过 record id 获取该卡所属的泳道 code。
     */
    _getLaneCodeByRecordId(recordId) {
        const groups = this.props.list?.groups || [];
        for (const group of groups) {
            const laneId = group.value ?? null;
            if (!laneId) {
                continue;
            }
            const laneCode = this._laneCodeCache.get(laneId);
            if (!laneCode) {
                continue;
            }
            if (group.list?.records) {
                const found = group.list.records.find(
                    (r) => String(r.id) === String(recordId)
                );
                if (found) {
                    return laneCode;
                }
            }
        }
        return null;
    }

    // ── useSortable 钩子已由父类 setup() 注册，这里覆盖生命周期方法 ───────────────

    /**
     * 拖拽开始时：捕获源卡片所在的泳道 code
     * @override
     */
    async sortStart({ element }) {
        super.sortStart(...arguments);

        // 确保泳道缓存已加载（可能 view 刚挂载时还没完成）
        if (this._laneCodeCache.size === 0) {
            await this._buildLaneCache();
        }

        this._dragInfo.sourceRecordId = element.dataset.id;
        this._dragInfo.sourceGroupId = element.closest('.o_kanban_group')?.dataset.id;
        this._dragInfo.sourceLaneCode = this._getLaneCodeByRecordId(element.dataset.id);
    }

    /**
     * 拖拽结束放置时：拦截跨泳道 drop，触发业务 RPC
     * @override
     */
    async sortRecordDrop(dataRecordId, dataGroupId, { element, parent }) {
        const sourceLaneCode = this._dragInfo.sourceLaneCode;

        // 通过目标泳道 group 的 datapoint id 找到 lane code
        const targetGroupId = parent?.dataset?.id;
        const targetLaneCode = targetGroupId
            ? this._getLaneCodeByGroupId(targetGroupId)
            : null;

        // 场景：waybill 泳道的卡片 → 换单/清关泳道
        if (sourceLaneCode === 'waybill' && targetLaneCode) {
            // 用 dataRecordId（sortable 回调参数，比 DOM 更可靠）找 waybill_id
            const waybillId = this._getWaybillIdFromRecord(dataRecordId);

            if (targetLaneCode === 'handover' && waybillId) {
                await this._createHandover(waybillId, parent);
                return; // 不走原生 moveRecord
            }
            if (targetLaneCode === 'clearance' && waybillId) {
                await this._openClearanceWizard(waybillId, parent);
                return; // 不走原生 moveRecord
            }
        }

        // 其他情况：换单/清关卡片同组排序，或 waybill → waybill → 走原生
        await super.sortRecordDrop(...arguments);
    }

    /**
     * 拖拽结束时清理状态
     * @override
     */
    sortStop(params) {
        super.sortStop(...arguments);
        this._dragInfo = {
            sourceRecordId: null,
            sourceGroupId: null,
            sourceLaneCode: null,
        };
    }

    // 获取「提单 ID」以供拖拽创建换单/清关
    _getWaybillIdFromRecord(recordId) {
        const groups = this.props.list?.groups || [];
        for (const group of groups) {
            if (group.list?.records) {
                const record = group.list.records.find(
                    (r) => String(r.id) === String(recordId)
                );
                if (record) {
                    // Odoo many2one 字段，id 是数字主键
                    const waybill = record.data.waybill_id;
                    // waybill_id 格式：[id, name]  例如 [31, 'WB202507300031']
                    if (Array.isArray(waybill)) {
                        return waybill[0];
                    }
                    return waybill;
                }
            }
        }
        return null;
    }

    // ── 业务操作 ────────────────────────────────────────────────────────────
    // 创建换单
    async _createHandover(waybillId, groupEl) {
        if (this.isCreating) {
            return;
        }
        this.isCreating = true;
        groupEl?.classList.add('drag-over');

        try {
            await this.orm.call(
                'operation.workbench.card',
                'action_create_handover_from_waybill_lane',
                [waybillId]
            );
            this.notification.add('换单任务已生成', {
                type: 'success',
                title: '成功',
            });
//            刷新当前看板
            this.props.list.load();
//            重新打开整个页面（×）
//            this.action.doAction(this.props.action, { clearBreadcrumbs: false });

//        } catch (err) {
//            console.log('122',err)
//            this.notification.add('操作失败：' + (err.message || '未知错误'), {
//                type: 'danger',
//                title: '错误',
//            });
//        }
        } catch (err) {
            const msg =
                err?.data?.arguments?.[0] ||
                (err?.data?.message ? err.data.message.replace(/^odoo\.exceptions\.[^:]+:\s*/, "") : "") ||
                err?.message ||
                "未知错误";

            this.notification.add(`操作失败：${msg}`, {
                type: "danger",
                title: "错误",
            });
        } finally {
            this.isCreating = false;
            groupEl?.classList.remove('drag-over');
        }
    }

    // 创建清关（打开弹窗）
    async _openClearanceWizard(waybillId, groupEl) {
        if (this.isCreating) {
            return;
        }
        this.isCreating = true;
        groupEl?.classList.add('drag-over');

        try {
            const result = await this.orm.call(
                'operation.workbench.card',
                'action_open_clearance_wizard_from_waybill_lane',
                [waybillId]
            );
            if (result && typeof result === 'object') {
                await this.action.doAction(result, {
                    onClose: () => {
//                        this.action.doAction(this.props.action, { clearBreadcrumbs: false });
                        this.props.list.load();
                    },
                });
            }
        } catch (err) {
            const msg =
                err?.data?.arguments?.[0] ||
                (err?.data?.message ? err.data.message.replace(/^odoo\.exceptions\.[^:]+:\s*/, "") : "") ||
                err?.message ||
                "未知错误";

            this.notification.add(`操作失败：${msg}`, {
                type: "danger",
                title: "错误",
            });
        } finally {
            this.isCreating = false;
            groupEl?.classList.remove('drag-over');
        }
    }
}

export const workbenchKanbanView = {
    ...kanbanView,
    Renderer: WorkbenchKanbanRenderer,
};

registry.category('views').add('workbench_kanban', workbenchKanbanView);
