/** @odoo-module */

import { registry } from '@web/core/registry';
import { kanbanView } from '@web/views/kanban/kanban_view';
import { WaybillKanbanValidator } from './waybill_kanban_validator';

export const waybillKanbanView = {
    ...kanbanView,
    Renderer: WaybillKanbanValidator,
};

registry.category('views').add('waybill_kanban_validator', waybillKanbanView);
