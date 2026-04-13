/** @odoo-module **/

//注册首页看板
import { registry } from "@web/core/registry";
import { WdIffmWorkbench } from "./workbench_home_action";

registry.category("actions").add("wd_iffm_workbench", WdIffmWorkbench);
