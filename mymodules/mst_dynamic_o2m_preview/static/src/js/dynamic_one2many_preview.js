/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class DynamicOne2ManyPreview extends Component {
    static template = "mst_dynamic_o2m_preview.DynamicOne2ManyPreview";

    static props = {
        ...standardFieldProps,
        options: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");

        this.state = useState({
            allLines: [],
            loading: true,
            totalCount: 0,
            isExpanded: false, // 全局默认：表格收起，只显示行数提示
        });

        onWillStart(async () => {
            await this.loadLines(this.props);
        });

        onWillUpdateProps(async (nextProps) => {
            this.state.isExpanded = false; // 切换单据强制收起
            await this.loadLines(nextProps);
        });
    }

    get options() {
        return this.props.options || {};
    }

    get columns() {
        const fields = this.options.fields || [];
        const labels = this.options.labels || fields;
        const wrapFields = this.options.wrap_fields || [];
        return fields.map((fieldName, index) => ({
            name: fieldName,
            label: labels[index] || fieldName,
            wrap: wrapFields.includes(fieldName),
        }));
    }

    get maxPreviewRows() {
        return this.options.max_rows || 5;
    }

    get columnWidth() {
        return this.options.column_width || 140;
    }

    get wrapTextLength() {
        return this.options.wrap_text_length || 25;
    }

    get tableMinWidth() {
        const columnCount = this.columns.length || 1;
        return `${columnCount * this.columnWidth}px`;
    }

    get cellWidth() {
        return `${this.columnWidth}px`;
    }

    get toggleIcon() {
        return this.state.isExpanded ? "▲" : "▼";
    }

    get toggleText() {
        return `明细共${this.state.totalCount}行 ${this.toggleIcon}`;
    }

    async loadLines(props) {
        this.state.loading = true;
        try {
            const parentModel = props.record.resModel || props.record.model?.config?.resModel;
            const parentId = props.record.resId || props.record.data?.id;
            const fieldName = props.name;
            const columns = this.columns;

            if (!parentModel || !parentId || !fieldName || !columns.length) {
                this.state.allLines = [];
                this.state.totalCount = 0;
                return;
            }

            const fieldMeta = await this.orm.call(parentModel, "fields_get", [[fieldName], ["relation"]]);
            const relationModel = fieldMeta?.[fieldName]?.relation;
            if (!relationModel) {
                this.state.allLines = [];
                this.state.totalCount = 0;
                return;
            }

            const parentRes = await this.orm.read(parentModel, [parentId], [fieldName]);
            const lineIds = parentRes[0][fieldName] || [];
            this.state.totalCount = lineIds.length;

            if (!lineIds.length) {
                this.state.allLines = [];
                return;
            }

            const readFields = this.columns.map(col => col.name);
            this.state.allLines = await this.orm.read(relationModel, lineIds, readFields);
        } catch (err) {
            console.error("O2M预览加载异常", err);
            this.state.allLines = [];
            this.state.totalCount = 0;
        } finally {
            this.state.loading = false;
        }
    }

    toggleExpand() {
        this.state.isExpanded = !this.state.isExpanded;
    }

    getCellValue(line, column) {
        const val = line[column.name];
        if ([null, undefined, false].includes(val)) return "";
        if (Array.isArray(val)) return val[1] || "";
        if (typeof val === "object" && val.display_name) return val.display_name;
        return val;
    }

    shouldWrapCell(line, column) {
        const text = String(this.getCellValue(line, column) || "");
        return column.wrap || text.length > this.wrapTextLength;
    }

    getCellClass(line, column) {
        return this.shouldWrapCell(line, column)
            ? "o_dynamic_o2m_cell o_dynamic_o2m_cell_wrap"
            : "o_dynamic_o2m_cell";
    }
}

registry.category("fields").add("dynamic_one2many_preview", {
    component: DynamicOne2ManyPreview,
    extractProps: ({ options }) => ({ options: options || {} }),
});