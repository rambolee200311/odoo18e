/** @odoo-module */

import { KanbanRecord } from '@web/views/kanban/kanban_record';

/**
 * 工作台看板卡片组件。
 * 只给 waybill 泳道的卡片加上 .o_draggable（可拖拽），
 * 换单/清关泳道的卡片保持不可拖拽（依赖 useSortable 的 .o_draggable 选择器）。
 */
export class WorkbenchKanbanRecord extends KanbanRecord {
    getRecordClasses() {
        const classes = super.getRecordClasses();

        // cardLaneCode 来自 this.record（在 onWillUpdateProps/onMounted 时由 useRecordObserver 填充）
        // record.data.lane_code.raw_value 才是 "waybill" / "handover" / "clearance"
        const rawData = this.record?.lane_code?.raw_value;
        const isWaybillCard = rawData === 'waybill';

        if (!isWaybillCard) {
            // 移除可能从父类继承的 o_draggable
            return classes.replace('o_draggable', '').trim();
        }

        return classes;
    }
}
