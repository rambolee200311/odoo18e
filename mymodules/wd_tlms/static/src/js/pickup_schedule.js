/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

function formatLocalDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

export class TransportPlan extends Component {
    static template = "wd_tlms.TransportPlanTemplate";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            plans: [],
            calendarDays: [],
            dailyPlans: {},
            currentMonth: new Date(),
        });

        let dragged = null;

        this.changeMonth = (delta) => {
            const cur = this.state.currentMonth;
            const d = new Date(cur.getFullYear(), cur.getMonth(), 1);
            d.setMonth(d.getMonth() + delta);
            this.state.currentMonth = d;
            this.initCalendar();
        };

        onWillStart(async () => {
            await this.loadData();
            this.initCalendar();
        });

        this.openPlanForm = () => {
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'pickup.plan',
                view_mode: 'tree,form',
                target: 'current',
            });
        };

        this.onDragStart = (ev, planId) => {
            dragged = { from: "list", planId: Number(planId) };
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", String(planId));
        };

        this.onDragOver = (ev) => {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
        };

        this.onDrop = async (ev, dateStr) => {
            ev.preventDefault();
            if (!dateStr) { dragged = null; return; }
            const planId = Number(ev.dataTransfer.getData("text/plain")) || dragged?.planId;
            if (dragged?.from === "calendar" && dragged?.planId) {
                await this.movePlan(dragged.planId, dateStr, dragged?.planDate);
            } else if (planId && Number.isFinite(planId) && planId > 0) {
                await this.savePlan(planId, dateStr);
            }
            dragged = null;
        };

        this.onPlanDragStart = (ev, planId, planDate) => {
            ev.stopPropagation();
            dragged = { from: "calendar", planId: Number(planId), planDate };
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", String(planId));
        };

        this.onPlanListDrop = async (ev) => {
            ev.preventDefault();
            const planId = Number(ev.dataTransfer.getData("text/plain")) || dragged?.planId;
            if (planId && Number.isFinite(planId) && planId > 0) {
                await this.cancelPlan(planId, dragged?.planId);
            }
            dragged = null;
        };
    }

    initCalendar() {
        const year = this.state.currentMonth.getFullYear();
        const month = this.state.currentMonth.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const days = [];
        for (let i = 0; i < firstDay.getDay(); i++) {
            days.push({ isEmpty: true, key: `empty-${year}-${month}-${i}` });
        }
        for (let d = 1; d <= lastDay.getDate(); d++) {
            const date = new Date(year, month, d);
            const dateStr = formatLocalDate(date);
            days.push({
                isEmpty: false, date: d, dateStr, fullDate: date,
                dayOfWeek: date.getDay(), key: dateStr,
            });
        }
        this.state.calendarDays = days;
        this.loadDailyPlans();
    }

    async loadData() {
        try {
            const plans = await this.orm.searchRead('pickup.plan',
                [['scheduled_date', '=', false]],
                ['id', 'name']);
            const result = [];
            for (const p of (plans || [])) {
                const item = { id: p.id, plan_id: p.id, name: p.name,
                    container_no: p.name, bl_no: '', container_type: '' };
                const lines = await this.orm.searchRead('pickup.plan.container.line',
                    [['plan_id', '=', p.id]],
                    ['container_number', 'bl_number', 'container_type']);
                if (lines && lines.length) {
                    item.container_no = lines[0].container_number || p.name;
                    item.bl_no = lines[0].bl_number || '';
                    item.container_type = lines[0].container_type || '';
                }
                result.push(item);
            }
            this.state.plans = result;
        } catch (error) {
            console.error("loadData error:", error);
            this.state.plans = [];
        }
    }

    async loadDailyPlans() {
        try {
            const year = this.state.currentMonth.getFullYear();
            const month = this.state.currentMonth.getMonth();
            const start = formatLocalDate(new Date(year, month, 1));
            const end = formatLocalDate(new Date(year, month + 1, 1));

            const plans = await this.orm.searchRead('pickup.plan',
                [['scheduled_date', '>=', start], ['scheduled_date', '<', end]],
                ['id', 'name', 'scheduled_date']);

            const summary = {};
            for (const p of (plans || [])) {
                if (!summary[p.scheduled_date]) summary[p.scheduled_date] = { count: 0, plans: [] };
                summary[p.scheduled_date].count++;
                summary[p.scheduled_date].plans.push({
                    id: p.id, name: p.name,
                    container_id: [p.id, p.name],
                    container_no: p.name,
                });
            }
            this.state.dailyPlans = summary;
            await this.loadData();
        } catch (error) {
            console.error('loadDailyPlans error:', error);
            this.state.dailyPlans = {};
        }
    }

    async savePlan(planId, planDate) {
        try {
            await this.orm.write('pickup.plan', [planId], { scheduled_date: planDate });
            await this.loadDailyPlans();
        } catch (error) {
            console.error('savePlan error:', error);
        }
    }

    async cancelPlan(containerId, planId) {
        try {
            const ids = planId && Number.isFinite(Number(planId)) ? [Number(planId)] : [];
            if (ids.length) {
                await this.orm.write('pickup.plan', ids, { scheduled_date: false });
            }
            await this.loadDailyPlans();
        } catch (error) {
            console.error('cancelPlan error:', error);
        }
    }

    async movePlan(planId, newDate, fromDate) {
        try {
            if (fromDate && newDate === fromDate) return;
            await this.orm.write('pickup.plan', [Number(planId)], { scheduled_date: newDate });
            await this.loadDailyPlans();
        } catch (error) {
            console.error('movePlan error:', error);
        }
    }

    getDayPlans(dateStr) {
        const entry = this.state.dailyPlans[dateStr];
        if (!entry) return { count: 0, plans: [] };
        const containersRaw = Array.isArray(entry.plans) ? entry.plans : [];
        const seen = new Set();
        const plans = [];
        for (const c of containersRaw) {
            const id = c?.id;
            if (!Number.isFinite(Number(id)) || seen.has(id)) continue;
            seen.add(id);
            plans.push(c);
        }
        return { count: entry.count, plans };
    }

    formatMonthYear() {
        const d = this.state.currentMonth;
        return `${d.getFullYear()}年${d.getMonth() + 1}月`;
    }

    getDayClass(day) {
        if (day?.isEmpty) return "o_calendar_day_empty";
        return (day?.dayOfWeek === 0 || day?.dayOfWeek === 6) ? "o_weekend" : "";
    }
}

registry.category("actions").add("tlmp_schedule.action", TransportPlan);
export { TransportPlan };
