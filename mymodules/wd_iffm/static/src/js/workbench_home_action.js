/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { View } from "@web/views/view";

//切换进口货代首页视图
export class WdIffmWorkbench extends Component {
    static template = "wd_iffm.wd_iffm_workbench_template";
    static components = { View };

    setup() {
        this.viewService = this.env.services.view;

        this.state = useState({
            activeTab: "waybill_near_due",
            activeView: "kanban",  // 默认显示看板视图
            filters: {
                project_id: "",
                shipping_company_id: "",
                eta_date_from: "",
                eta_date_to: ""
            },
            // 下拉选项（静态数据，用于UI展示）
            projectOptions: [
                { id: 1, name: "项目A" },
                { id: 2, name: "项目B" },
                { id: 3, name: "项目C" }
            ],
            shippingCompanyOptions: [
                { id: 1, name: "马士基航运" },
                { id: 2, name: "地中海航运" },
                { id: 3, name: "中远海运" },
                { id: 4, name: "达飞轮船" }
            ],
            dashboardData: {
                waybill: { near_due_count: 0, overdue_count: 0 },
                handover: { near_due_count: 0, overdue_count: 0 },
                clearance: { near_due_count: 0, overdue_count: 0 },
                total: { all_count: 0, near_due_count: 0, overdue_count: 0 }
            },
            viewProps: null,
            currentResModel: null,
            currentDomain: []
        });

        // 所有卡片都跳转到提单看板视图，只是 domain 不同
        this.cardConfigs = {
            // 临期提单
            waybill_near_due: {
                res_model: "world.depot.waybill",
                domain: [],
                label: "临期提单"
            },
            // 逾期提单
            waybill_overdue: {
                res_model: "world.depot.waybill",
                domain: [],
                label: "逾期提单"
            },
            // 临期换单
            handover_near_due: {
                res_model: "world.depot.waybill",
                domain: [],
                label: "临期换单"
            },
            // 逾期换单
            handover_overdue: {
                res_model: "world.depot.waybill",
                domain: [],
                label: "逾期换单"
            },
            // 临期清关
            clearance_near_due: {
                res_model: "world.depot.waybill",
                domain: [],
                label: "临期清关"
            },
            // 逾期清关
            clearance_overdue: {
                res_model: "world.depot.waybill",
                domain: [],
                label: "逾期清关"
            },
            // 全部提单
            waybill_all: {
                res_model: "world.depot.waybill",
                domain: [],
                label: "全部提单"
            }
        };

        this.onCardClick = this.onCardClick.bind(this);
        this.onViewTypeClick = this.onViewTypeClick.bind(this);
        this.onFilterChange = this.onFilterChange.bind(this);
        this.clearFilters = this.clearFilters.bind(this);
        this.onViewRecordClicked = this.onViewRecordClicked.bind(this);

        onWillStart(async () => {
            await this.loadDashboardData();
            await this.loadView(this.state.activeTab);
        });
    }

    async onViewRecordClicked(record) {
        console.log(1211)
        const actionService = this.env.services.action;
        await actionService.doAction({
            type: "ir.actions.act_window",
            name: "提单详情",
            res_model: this.state.currentResModel,
            res_id: record.resId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }

    onFilterChange(field, value) {
        this.state.filters[field] = value;
        // 后端支持 filters 参数后启用
        // this.applyFilters();
    }

    clearFilters() {
        this.state.filters = {
            project_id: "",
            shipping_company_id: "",
            eta_date_from: "",
            eta_date_to: ""
        };
        // 后端支持 filters 参数后启用
        // this.applyFilters();
    }

    async applyFilters() {
        // 重新加载 dashboard 数据和视图，带上 filters 作为 domain
        console.log("应用筛选条件:", this.state.filters);
        // await this.loadDashboardData();  // 后端需要支持 filters 参数
        // await this.loadView(this.state.activeTab);
    }

    async loadDashboardData() {
        const orm = this.env.services.orm;
        try {
            const data = await orm.call(
                "operation.workbench.dashboard.data",
                "get_dashboard_counts",
                []
            );
            this.state.dashboardData = data;
        } catch (err) {
//            console.error("加载仪表盘数据失败:", error);
            const msg =
                err?.data?.arguments?.[0] ||
                (err?.data?.message ? err.data.message.replace(/^odoo\.exceptions\.[^:]+:\s*/, "") : "") ||
                err?.message ||
                "未知错误";

//            this.notification.add(`操作失败：${msg}`, {
//                type: "danger",
//                title: "错误",
//            });
            console.error("加载仪表盘数据失败:", msg);

            this.state.dashboardData = {
                waybill: { near_due_count: 0, overdue_count: 0 },
                handover: { near_due_count: 0, overdue_count: 0 },
                clearance: { near_due_count: 0, overdue_count: 0 },
                total: { all_count: 0, near_due_count: 0, overdue_count: 0 }
            };
        }
    }

    async loadLaneRecordIds(laneCode) {
        const orm = this.env.services.orm;
        try {
            const data = await orm.call(
                "operation.workbench.dashboard.data",
                "get_lane_record_ids",
                [laneCode]
            );
            if (data && data.ids && data.ids.length > 0) {
                return data.ids;
            }
        } catch (error) {
            console.error(`加载车道 ${laneCode} 记录ID失败:`, error);
        }
        return [];
    }

    async onCardClick(lane, type) {
        const tabId = `${lane}_${type}`;
        if (this.state.activeTab === tabId) {
            return;
        }
        this.state.activeTab = tabId;
        await this.loadView(tabId);
    }

    async onViewTypeClick(viewType) {
        if (this.state.activeView === viewType) {
            return;
        }
        this.state.activeView = viewType;
        await this.loadView(this.state.activeTab);
    }

    async loadView(tabId) {
        const config = this.cardConfigs[tabId];
        if (!config) {
            console.error(`未找到 Tab ID: ${tabId} 的配置`);
            return;
        }

        this.state.viewProps = null;
        this.state.currentResModel = config.res_model;

        try {
            let domain = [];

            // 全部提单不需要额外 domain，显示所有记录
            if (tabId !== 'waybill_all') {
                // 获取记录ID列表
                const laneCode = tabId.split("_")[0];
                const recordIds = await this.loadLaneRecordIds(laneCode);

                if (recordIds.length > 0) {
                    domain = [["id", "in", recordIds]];
                }
            }

            this.state.currentDomain = domain;

            // 加载视图信息
            const viewInfo = await this.viewService.loadViews({
                resModel: config.res_model,
                views: [[false, this.state.activeView]],
            });

            let finalViewType = this.state.activeView;

            // 如果指定视图不存在，尝试其他视图
            if (!viewInfo.views[this.state.activeView]) {
                if (viewInfo.views.kanban) {
                    finalViewType = "kanban";
                    this.state.activeView = "kanban";
                } else if (viewInfo.views.list) {
                    finalViewType = "list";
                    this.state.activeView = "list";
                }
            }

            this.state.viewProps = {
                resModel: config.res_model,
                type: finalViewType,
                display: {},
                context: {},
                domain: domain,
                selectRecord: (resId) => {
                    this.onViewRecordClicked({ resId });
                },
                searchViewId: viewInfo.views[finalViewType]?.searchViewId,
                action: {
                    id: false,
                    name: config.label || "提单列表",
                    res_model: config.res_model,
                    type: "ir.actions.act_window",
                    view_mode: `${finalViewType},form`,
                    views: [
                        [viewInfo.views[finalViewType]?.id || false, finalViewType],
                        [false, "form"],
                    ],
                },
            };
        } catch (error) {
            console.error("加载视图失败:", error);
            this.state.viewProps = null;
        }
    }

    getCurrentTab() {
        const config = this.cardConfigs[this.state.activeTab];
        return {
            label: config ? config.label : this.state.activeTab,
            type: this.state.activeTab.includes("near_due") ? "临期" : 
                  this.state.activeTab.includes("overdue") ? "逾期" : "全部"
        };
    }
}