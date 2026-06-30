/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class TransportPlan extends Component {
    static template = "transport.TransportPlanTemplate";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // 用于打开标准的 bl.container 界面
        this.action = useService("action");
        
        this.state = useState({
            containers: [],           // 左侧待安排集装箱列表
            calendarDays: [],         // 日历天数数组
            dailyPlans: {},           // 每日计划汇总 {日期: {count: 数量, containers: []}}
            currentMonth: new Date(), // 当前显示的月份
            // 筛选条件
            selectedBlNo: '',         // 选中的提单号
            selectedWarehouseId: null, // 选中的目标仓库 ID
            // 下拉选项
            blNoOptions: [],          // 提单号选项列表
            warehouseOptions: [],    // 仓库选项列表
        });

        // 拖拽上下文（非 reactive）：避免拖拽过程中因渲染/状态变化导致“拖拽目标”丢失
        // 参考 web/kanban：drag 期间用普通变量存身份，drop 后再触发数据刷新
        let dragged = null; // { from: "list"|"calendar", containerId: number, planId?: number, planDate?: string }

        // 绑定方法：避免模板事件回调里调用时丢失 this
        this.changeMonth = (delta) => {
            const cur = this.state.currentMonth;
            const newDate = new Date(cur.getFullYear(), cur.getMonth(), 1);
            newDate.setMonth(newDate.getMonth() + delta);
            this.state.currentMonth = newDate;
            this.initCalendar();
        };

        onWillStart(async () => {
            await this.loadData();
            this.initCalendar();
        });

        // 打开集装箱标准表单/列表视图
        this.openContainerForm = () => {
            // TODO: 将下面的 external ID 替换为你实际的 bl.container action 外部 ID
            // 例如： "transport.action_bl_container" 或 其他模块中定义的 action
            this.action.doAction("transport.action_bl_container");
        };

        // 拖拽事件处理
        this.onDragStart = (ev, containerId) => {
            dragged = { from: "list", containerId: Number(containerId) };
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", String(containerId));
        };

        this.onDragOver = (ev) => {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
        };

        this.onDrop = async (ev, dateStr) => {
            ev.preventDefault();
            // 空白格（leading blanks）不接收 drop，避免触发不必要的 patch/错误
            if (!dateStr) {
                dragged = null;
                return;
            }
            const idFromTransfer = Number(ev.dataTransfer.getData("text/plain"));
            const containerId = Number.isFinite(idFromTransfer) && idFromTransfer > 0 ? idFromTransfer : dragged?.containerId;
            if (dragged?.from === "calendar" && dragged?.planId) {
                await this.moveTransportPlan(dragged.planId, dateStr, dragged?.planDate);
            } else if (containerId) {
                await this.saveTransportPlan(containerId, dateStr);
            }
            dragged = null;
        };

        // 从日历拖回左侧
        this.onPlanDragStart = (ev, planId, containerId, planDate) => {
            ev.stopPropagation();
            dragged = { from: "calendar", planId: Number(planId), containerId: Number(containerId), planDate };
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", String(containerId));
        };

        this.onContainerListDrop = async (ev) => {
            ev.preventDefault();
            const idFromTransfer = Number(ev.dataTransfer.getData("text/plain"));
            const containerId = Number.isFinite(idFromTransfer) && idFromTransfer > 0 ? idFromTransfer : dragged?.containerId;
            if (containerId) {
                await this.cancelTransportPlan(containerId, dragged?.planId);
            }
            dragged = null;
        };
    }

    /**
     * 初始化日历
     */
    initCalendar() {
        const year = this.state.currentMonth.getFullYear();
        const month = this.state.currentMonth.getMonth();
    
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
    
        const days = [];
    
        // 关键：首周补空位，让 1 号对齐到正确星期
        const leadingBlanks = firstDay.getDay(); // 0=周日..6=周六
        for (let i = 0; i < leadingBlanks; i++) {
            days.push({
                isEmpty: true,
                key: `empty-${year}-${month}-${i}`,
            });
        }
    
        for (let d = 1; d <= lastDay.getDate(); d++) {
            const date = new Date(year, month, d);
            const dateStr = date.toISOString().split("T")[0];
            days.push({
                isEmpty: false,
                date: d,
                dateStr,
                fullDate: date,
                dayOfWeek: date.getDay(),
                key: dateStr,
            });
        }
        
        this.state.calendarDays = days;
        this.loadDailyPlans();
    }

    /**
     * 加载数据
     */
    async loadData() {
        try {
            const containers = await this.orm.call(
                "bl.container",
                "get_unplanned_containers",
                []
            );
            this.state.containers = containers || [];
            // 加载筛选选项
            await this.loadFilterOptions();
        } catch (error) {
            console.error("加载数据失败:", error);
            this.state.containers = [];
            this.notification.add("加载数据失败，请联系管理员或稍后重试", { type: "danger" });
        }
    }

    /**
     * 加载筛选下拉选项
     */
    async loadFilterOptions() {
        try {
            // 获取所有待安排集装箱
            const containers = await this.orm.call(
                "bl.container",
                "get_unplanned_containers",
                []
            );
            if (!containers || !Array.isArray(containers)) {
                return;
            }

            // 提取唯一的提单号
            const blNos = [...new Set(containers.map(c => c.bl_no).filter(Boolean))].sort();
            this.state.blNoOptions = blNos.map(bl_no => ({ value: bl_no, label: bl_no }));

            // 提取唯一的目的仓库（需要通过 warehouse id 获取 name）
            const warehouseIds = [...new Set(
                containers
                    .map(c => c.destination_warehouse)
                    .filter(id => id && typeof id === 'number')
            )];

            if (warehouseIds.length > 0) {
                const warehouses = await this.orm.read(
                    "stock.warehouse",
                    warehouseIds,
                    ["id", "name"]
                );
                this.state.warehouseOptions = (warehouses || []).map(w => ({
                    value: w.id,
                    label: w.name
                }));
            } else {
                this.state.warehouseOptions = [];
            }
        } catch (error) {
            console.error("加载筛选选项失败:", error);
        }
    }

    /**
     * 获取筛选后的集装箱列表
     */
    getFilteredContainers() {
        let result = this.state.containers;

        // 按提单号筛选
        if (this.state.selectedBlNo) {
            result = result.filter(c => c.bl_no === this.state.selectedBlNo);
        }

        // 按目标仓库筛选
        if (this.state.selectedWarehouseId) {
            result = result.filter(c => c.destination_warehouse === this.state.selectedWarehouseId);
        }

        return result;
    }

    /**
     * 提单号筛选变更
     */
    onBlNoChange(ev) {
        this.state.selectedBlNo = ev.target.value;
        // 切换提单号时，清空仓库筛选
        this.state.selectedWarehouseId = null;
    }

    /**
     * 目标仓库筛选变更
     */
    onWarehouseChange(ev) {
        const value = ev.target.value;
        this.state.selectedWarehouseId = value ? parseInt(value) : null;
    }

    /**
     * 清空筛选
     */
    clearFilters() {
        this.state.selectedBlNo = '';
        this.state.selectedWarehouseId = null;
    }

    /**
     * 加载每日计划汇总
     */
    async loadDailyPlans() {
        try {
            const year = this.state.currentMonth.getFullYear();
            const month = this.state.currentMonth.getMonth();
            const startDate = new Date(year, month, 1).toISOString().split('T')[0];
            const endDate = new Date(year, month + 1, 0).toISOString().split('T')[0];
            
            const summary = await this.orm.call(
                'container.transport.plan',
                'get_daily_plan_summary',
                [startDate, endDate]
            );
            // 强制兜底：必须是对象映射 { [dateStr]: {count, containers} }
            this.state.dailyPlans = (summary && typeof summary === "object" && !Array.isArray(summary)) ? summary : {};
            
            // 刷新待安排列表（可能有集装箱被排期了）
            await this.loadData();
        } catch (error) {
            console.error('加载计划汇总失败:', error);
            this.state.dailyPlans = {};
        }
    }

    /**
     * 保存运输计划
     */
    async saveTransportPlan(containerId, planDate) {
        try {
            const validContainerId = parseInt(containerId);
            if (isNaN(validContainerId) || validContainerId <= 0) {
                this.notification.add("无效的集装箱ID", { type: "warning" });
                return;
            }

            await this.orm.call(
                'container.transport.plan',
                'create_transport_plan',
                [validContainerId, planDate]
            );

            // 刷新数据
            await this.loadDailyPlans();
            
            this.notification.add("运输计划创建成功", { type: "success" });
        } catch (error) {
            console.error('保存失败:', error);
            this.notification.add(`保存运输计划失败：${error.message || error}`, { type: "danger" });
        }
    }

    /**
     * 取消运输计划（拖回左侧）
     */
    async cancelTransportPlan(containerId, planId = null) {
        try {
            const validContainerId = parseInt(containerId);
            if (isNaN(validContainerId) || validContainerId <= 0) {
                this.notification.add("无效的集装箱ID", { type: "warning" });
                return;
            }

            // 优先用拖拽上下文里的 planId；否则按 containerId 批量删除（兼容历史重复数据）
            let planIds = [];
            if (planId && Number.isFinite(Number(planId))) {
                planIds = [Number(planId)];
            } else {
                const plans = await this.orm.searchRead(
                    'container.transport.plan',
                    [['container_id', '=', validContainerId]],
                    ['id']
                );
                planIds = (plans || []).map((p) => p.id).filter((id) => Number.isFinite(Number(id)));
            }

            if (!planIds.length) {
                return;
            }

            for (const id of planIds) {
                await this.orm.call('container.transport.plan', 'delete_transport_plan', [id]);
            }

            // 刷新数据
            await this.loadDailyPlans();
            this.notification.add("已取消运输计划", { type: "warning" });
        } catch (error) {
            console.error('取消计划失败:', error);
            this.notification.add(`取消计划失败：${error.message || error}`, { type: "danger" });
        }
    }

    /**
     * 日历内拖动：更新计划日期（避免重复 create 导致同格多卡）
     */
    async moveTransportPlan(planId, planDate, fromDate = null) {
        try {
            if (fromDate && planDate === fromDate) {
                this.notification.add("当前日期已排班", { type: "warning" });
                return;
            }

            const validPlanId = parseInt(planId);
            if (isNaN(validPlanId) || validPlanId <= 0) {
                this.notification.add("无效的计划ID", { type: "warning" });
                return;
            }

            await this.orm.call(
                "container.transport.plan",
                "update_transport_plan",
                [validPlanId, { plan_date: planDate }]
            );

            await this.loadDailyPlans();
            this.notification.add("运输计划已更新", { type: "success" });
        } catch (error) {
            console.error("更新计划失败:", error);
            this.notification.add(`更新计划失败：${error.message || error}`, { type: "danger" });
        }
    }

    /**
     * 获取某天的计划
     */
    getDayPlans(dateStr) {
        const plans = (this.state.dailyPlans && typeof this.state.dailyPlans === "object") ? this.state.dailyPlans : {};
        const entry = plans[dateStr];
        if (!entry || typeof entry !== "object") {
            return { count: 0, containers: [] };
        }
        // 兜底去重：同一天如果因历史数据/并发出现重复 plan.id，这里只渲染一份
        const containersRaw = Array.isArray(entry.containers) ? entry.containers : [];
        const seen = new Set();
        const containers = [];
        for (const c of containersRaw) {
            const id = c?.id;
            if (!Number.isFinite(Number(id)) || seen.has(id)) {
                continue;
            }
            seen.add(id);
            containers.push(c);
        }
        const count = Number.isFinite(entry.count) ? entry.count : containers.length;
        return { ...entry, count, containers };
    }

    /**
     * 格式化日期显示
     */
    formatMonthYear() {
        const year = this.state.currentMonth.getFullYear();
        const month = this.state.currentMonth.getMonth() + 1;
        return `${year}年${month}月`;
    }

    /**
     * 日历格子 class 统一由这里生成，避免 t-foreach 内部出现结构切换导致 VToggler 崩溃
     */
    getDayClass(day) {
        const classes = [];
        if (day?.isEmpty) {
            classes.push("o_calendar_day_empty");
        } else if (day?.dayOfWeek === 0 || day?.dayOfWeek === 6) {
            classes.push("o_weekend");
        }
        return classes.join(" ");
    }
}

registry.category("actions").add("transport_plan.action", TransportPlan);
export { TransportPlan };
