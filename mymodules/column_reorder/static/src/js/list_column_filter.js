/** @odoo-module **/

import {ListRenderer} from "@web/views/list/list_renderer";
import {Domain} from "@web/core/domain";
import {patch} from "@web/core/utils/patch";
import {onMounted, onWillUnmount, onPatched} from "@odoo/owl";

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);

        this.columnFilters = {};
        this.columnInfoMap = {};
        this._searchTimeout = null;
        this._searchRowInjected = false;
        this.baseGlobalDomain = Array.isArray(this.env?.searchModel?.globalDomain)
            ? [...this.env.searchModel.globalDomain]
            : [];

        try {
            if (this.props.list?.fields) {
                const fields = this.props.list.fields;
                Object.entries(fields).forEach(([name, fieldDef]) => {
                    let domainField = name;
                    const fieldType = fieldDef.type;
                    if (fieldType === "many2one" || fieldType === "many2many" || fieldType === "one2many") {
                        domainField = name + ".name";
                    }
                    this.columnInfoMap[name] = {
                        type: fieldType,
                        domainField: domainField,
                        label: fieldDef.string || name,
                        selection: fieldDef.selection || null,
                        relation: fieldDef.relation || null,
                    };
                });
            }
        } catch (e) {
            console.warn("CF setup error:", e);
        }

        onMounted(() => this._retryInject());
        onPatched(() => this._retryInject());
    },

    _retryInject(maxRetries) {
        if (this._searchRowInjected) return;
        if (maxRetries === undefined) maxRetries = 10;

        const rootEl = this.rootRef?.el;
        if (!rootEl) {
            if (maxRetries > 0) setTimeout(() => this._retryInject(maxRetries - 1), 100);
            return;
        }
        const thead = rootEl.querySelector("thead");
        if (!thead) {
            if (maxRetries > 0) setTimeout(() => this._retryInject(maxRetries - 1), 100);
            return;
        }
        const headerRow = thead.querySelector("tr");
        if (!headerRow || !headerRow.querySelector("th[data-name]")) {
            if (maxRetries > 0) setTimeout(() => this._retryInject(maxRetries - 1), 100);
            return;
        }
        if (thead.querySelector(".column_search_row")) {
            this._searchRowInjected = true;
            return;
        }
        this._injectSearchRow(thead, headerRow);
    },

    _injectSearchRow(thead, headerRow) {
        const searchRow = document.createElement("tr");
        searchRow.className = "column_search_row";

        headerRow.querySelectorAll("th").forEach((headerCell) => {
            const searchCell = document.createElement("th");
            searchCell.className = headerCell.className;
            const dataName = headerCell.getAttribute("data-name");
            if (!dataName) {
                searchRow.appendChild(searchCell);
                return;
            }
            const colInfo = this.columnInfoMap[dataName];
            if (!colInfo) {
                searchRow.appendChild(searchCell);
                return;
            }
            const wrapper = document.createElement("div");
            wrapper.className = "o_cf_wrapper";

            const widget = this._createFilterWidget(colInfo, dataName);
            if (widget) wrapper.appendChild(widget);

            searchCell.appendChild(wrapper);
            searchRow.appendChild(searchCell);
        });

        if (headerRow.nextSibling) {
            thead.insertBefore(searchRow, headerRow.nextSibling);
        } else {
            thead.appendChild(searchRow);
        }
        this._searchRowInjected = true;
        this._fetchFieldInfo();
    },

    _createFilterWidget(colInfo, fieldName) {
        switch (colInfo.type) {
            case "selection":
                return this._createSelectionWidget(colInfo, fieldName);
            case "boolean":
                return this._createBooleanWidget(colInfo, fieldName);
            case "integer":
            case "float":
            case "monetary":
                return this._createNumericWidget(colInfo, fieldName);
            case "date":
            case "datetime":
                return this._createDateWidget(colInfo, fieldName);
            case "many2one":
                return this._createRelationWidget(colInfo, fieldName);
            default:
                return this._createTextWidget(colInfo, fieldName);
        }
    },

    _createTextWidget(colInfo, fieldName) {
        const input = document.createElement("input");
        input.type = "text";
        input.className = "o_cf_input";
        input.placeholder = "..";
        input.title = colInfo.label + "\\n=exact  ^starts  ends$";
        this._setupInput(input, colInfo, fieldName);
        return input;
    },

    _createNumericWidget(colInfo, fieldName) {
        const input = document.createElement("input");
        input.type = "text";
        input.className = "o_cf_input";
        input.placeholder = "..";
        input.title = colInfo.label + "\\n>5  <10  >=1  <=99  5-20";
        this._setupInput(input, colInfo, fieldName);
        return input;
    },

    _createDateWidget(colInfo, fieldName) {
        const container = document.createElement("div");
        container.className = "o_cf_date_container";
        container.style.cssText = "display:flex;gap:2px;align-items:center;";

        // Quick date range selector
        const quickSelect = document.createElement("select");
        quickSelect.className = "o_cf_input o_cf_select";
        quickSelect.style.cssText = "flex:0 0 auto;max-width:85px;padding:2px 4px;font-size:11px;";

        const presets = [
            {v: "", l: ".."},
            {v: "today", l: "Today"},
            {v: "yesterday", l: "Yesterday"},
            {v: "this_week", l: "This Week"},
            {v: "last_week", l: "Last Week"},
            {v: "this_month", l: "This Month"},
            {v: "last_month", l: "Last Month"},
            {v: "past_7", l: "Past 7 Days"},
            {v: "past_30", l: "Past 30 Days"},
            {v: "custom", l: "Custom.."},
        ];

        presets.forEach(function (item) {
            const opt = document.createElement("option");
            opt.value = item.v;
            opt.textContent = item.l;
            quickSelect.appendChild(opt);
        });

        // From / To date inputs (hidden by default)
        const rangeContainer = document.createElement("div");
        rangeContainer.className = "o_cf_date_range";
        rangeContainer.style.cssText = "display:none;gap:2px;align-items:center;";

        const fromInput = document.createElement("input");
        fromInput.type = "date";
        fromInput.className = "o_cf_input";
        fromInput.style.cssText = "flex:1;min-width:0;padding:2px 4px;font-size:11px;";

        const sep = document.createElement("span");
        sep.textContent = "~";
        sep.style.cssText = "font-size:10px;color:#666;";

        const toInput = document.createElement("input");
        toInput.type = "date";
        toInput.className = "o_cf_input";
        toInput.style.cssText = "flex:1;min-width:0;padding:2px 4px;font-size:11px;";

        rangeContainer.appendChild(fromInput);
        rangeContainer.appendChild(sep);
        rangeContainer.appendChild(toInput);

        container.appendChild(quickSelect);
        container.appendChild(rangeContainer);

        // Restore saved value
        if (this.columnFilters[fieldName]) {
            const saved = this.columnFilters[fieldName];
            if (saved === "custom" && saved.from && saved.to) {
                quickSelect.value = "custom";
                fromInput.value = saved.from;
                toInput.value = saved.to;
                rangeContainer.style.display = "flex";
            } else {
                quickSelect.value = saved;
            }
            quickSelect.classList.add("has-value");
        }

        const self = this;
        const applyFilter = function () {
            const sel = quickSelect.value;
            if (!sel) {
                delete self.columnFilters[fieldName];
                quickSelect.classList.remove("has-value");
                rangeContainer.style.display = "none";
            } else if (sel === "custom") {
                rangeContainer.style.display = "flex";
                const fromVal = fromInput.value;
                const toVal = toInput.value;
                if (fromVal && toVal) {
                    self.columnFilters[fieldName] = "custom:" + fromVal + "," + toVal;
                    quickSelect.classList.add("has-value");
                } else {
                    delete self.columnFilters[fieldName];
                }
            } else {
                self.columnFilters[fieldName] = sel;
                quickSelect.classList.add("has-value");
                rangeContainer.style.display = "none";
            }
            self._debounceFilter();
        };

        quickSelect.addEventListener("change", applyFilter);
        fromInput.addEventListener("change", applyFilter);
        toInput.addEventListener("change", applyFilter);

        return container;
    },

    _createSelectionWidget(colInfo, fieldName) {
        const select = document.createElement("select");
        select.className = "o_cf_input o_cf_select";

        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "..";
        select.appendChild(blank);

        if (colInfo.selection) {
            colInfo.selection.forEach(function (item) {
                const opt = document.createElement("option");
                opt.value = item[0];
                opt.textContent = item[1];
                select.appendChild(opt);
            });
        }

        if (this.columnFilters[fieldName]) {
            select.value = this.columnFilters[fieldName];
            select.classList.add("has-value");
        }

        select.addEventListener("change", (ev) => {
            const val = ev.target.value;
            if (val) {
                this.columnFilters[fieldName] = val;
                ev.target.classList.add("has-value");
            } else {
                delete this.columnFilters[fieldName];
                ev.target.classList.remove("has-value");
            }
            this._debounceFilter();
        });

        return select;
    },

    _createBooleanWidget(colInfo, fieldName) {
        const select = document.createElement("select");
        select.className = "o_cf_input o_cf_select";

        [["", ".."], ["true", "Yes"], ["false", "No"]].forEach(function (item) {
            const opt = document.createElement("option");
            opt.value = item[0];
            opt.textContent = item[1];
            select.appendChild(opt);
        });

        if (this.columnFilters[fieldName]) {
            select.value = this.columnFilters[fieldName];
            select.classList.add("has-value");
        }

        select.addEventListener("change", (ev) => {
            const val = ev.target.value;
            if (val) {
                this.columnFilters[fieldName] = val;
                ev.target.classList.add("has-value");
            } else {
                delete this.columnFilters[fieldName];
                ev.target.classList.remove("has-value");
            }
            this._debounceFilter();
        });

        return select;
    },

    _createRelationWidget(colInfo, fieldName) {
        const input = document.createElement("input");
        input.type = "text";
        input.className = "o_cf_input";
        input.placeholder = "..";
        input.title = colInfo.label;
        this._setupInput(input, colInfo, fieldName);
        return input;
    },

    _setupInput(input, colInfo, fieldName) {
        if (this.columnFilters[fieldName]) {
            input.value = this.columnFilters[fieldName];
            input.classList.add("has-value");
        }
        input.addEventListener("input", (ev) => {
            const val = ev.target.value.trim();
            if (val) {
                this.columnFilters[fieldName] = val;
                ev.target.classList.add("has-value");
            } else {
                delete this.columnFilters[fieldName];
                ev.target.classList.remove("has-value");
            }
            this._debounceFilter();
        });
    },

    _debounceFilter() {
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => this._applyColumnFilters(), 300);
    },

    _buildDomain() {
        const domain = [];
        for (const [fieldName, searchValue] of Object.entries(this.columnFilters)) {
            if (!searchValue) continue;
            const colInfo = this.columnInfoMap[fieldName];
            if (!colInfo) continue;
            const fieldPath = colInfo.domainField;
            const fieldType = colInfo.type;
            let conditions = [];

            switch (fieldType) {
                case "char":
                case "text":
                    if (searchValue.startsWith("=")) {
                        conditions = [[fieldPath, "=", searchValue.slice(1)]];
                    } else if (searchValue.startsWith("^")) {
                        conditions = [[fieldPath, "=like", searchValue.slice(1) + "%"]];
                    } else if (searchValue.endsWith("$")) {
                        conditions = [[fieldPath, "=like", "%" + searchValue.slice(0, -1)]];
                    } else if (searchValue.includes("*")) {
                        conditions = [[fieldPath, "=like", searchValue.replace(/\\*/g, "%")]];
                    } else {
                        conditions = [[fieldPath, "ilike", searchValue]];
                    }
                    break;

                case "integer":
                case "float":
                case "monetary": {
                    const rangeMatch = searchValue.match(/^(\\d+)\\s*-\\s*(\\d+)$/);
                    const gtMatch = searchValue.match(/^>=\\s*(\\d+(?:\\.\\d+)?)$/);
                    const gt2Match = searchValue.match(/^>\\s*(\\d+(?:\\.\\d+)?)$/);
                    const ltMatch = searchValue.match(/^<=\\s*(\\d+(?:\\.\\d+)?)$/);
                    const lt2Match = searchValue.match(/^<\\s*(\\d+(?:\\.\\d+)?)$/);

                    if (rangeMatch) {
                        conditions = [[fieldPath, ">=", parseFloat(rangeMatch[1])], [fieldPath, "<=", parseFloat(rangeMatch[2])]];
                    } else if (gtMatch) {
                        conditions = [[fieldPath, ">=", parseFloat(gtMatch[1])]];
                    } else if (gt2Match) {
                        conditions = [[fieldPath, ">", parseFloat(gt2Match[1])]];
                    } else if (ltMatch) {
                        conditions = [[fieldPath, "<=", parseFloat(ltMatch[1])]];
                    } else if (lt2Match) {
                        conditions = [[fieldPath, "<", parseFloat(lt2Match[1])]];
                    } else if (searchValue.startsWith("=")) {
                        conditions = [[fieldPath, "=", parseFloat(searchValue.slice(1))]];
                    } else {
                        const num = parseFloat(searchValue);
                        if (!isNaN(num)) conditions = [[fieldPath, "=", num]];
                    }
                    break;
                }

                case "date":
                case "datetime": {
                    const todayStr = function () {
                        var d = new Date();
                        return d.toISOString().split("T")[0];
                    };
                    var d = new Date();

                    // Handle custom:from,to format from date widget
                    if (searchValue.startsWith("custom:")) {
                        var parts = searchValue.substring(7).split(",");
                        if (parts.length === 2 && parts[0] && parts[1]) {
                            conditions = [[fieldPath, ">=", parts[0]], [fieldPath, "<=", parts[1]]];
                        }
                        break;
                    }

                    switch (searchValue) {
                        case "today":
                            conditions = [[fieldPath, "=", todayStr()]];
                            break;
                        case "yesterday":
                            d.setDate(d.getDate() - 1);
                            conditions = [[fieldPath, "=", d.toISOString().split("T")[0]]];
                            break;
                        case "this_week": {
                            var monday = new Date(d);
                            monday.setDate(d.getDate() - d.getDay() + 1);
                            var sunday = new Date(monday);
                            sunday.setDate(monday.getDate() + 6);
                            conditions = [[fieldPath, ">=", monday.toISOString().split("T")[0]], [fieldPath, "<=", sunday.toISOString().split("T")[0]]];
                            break;
                        }
                        case "last_week": {
                            d.setDate(d.getDate() - 7);
                            var monday = new Date(d);
                            monday.setDate(d.getDate() - d.getDay() + 1);
                            var sunday = new Date(monday);
                            sunday.setDate(monday.getDate() + 6);
                            conditions = [[fieldPath, ">=", monday.toISOString().split("T")[0]], [fieldPath, "<=", sunday.toISOString().split("T")[0]]];
                            break;
                        }
                        case "this_month": {
                            var first = new Date(d.getFullYear(), d.getMonth(), 1);
                            var last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
                            conditions = [[fieldPath, ">=", first.toISOString().split("T")[0]], [fieldPath, "<=", last.toISOString().split("T")[0]]];
                            break;
                        }
                        case "last_month": {
                            var first = new Date(d.getFullYear(), d.getMonth() - 1, 1);
                            var last = new Date(d.getFullYear(), d.getMonth(), 0);
                            conditions = [[fieldPath, ">=", first.toISOString().split("T")[0]], [fieldPath, "<=", last.toISOString().split("T")[0]]];
                            break;
                        }
                        case "past_7":
                            d.setDate(d.getDate() - 7);
                            conditions = [[fieldPath, ">=", d.toISOString().split("T")[0]]];
                            break;
                        case "past_30":
                            d.setDate(d.getDate() - 30);
                            conditions = [[fieldPath, ">=", d.toISOString().split("T")[0]]];
                            break;
                        default: {
                            var rangeDate = searchValue.match(/^(\\d{4}-\\d{2}-\\d{2})\\.\\.(\\d{4}-\\d{2}-\\d{2})$/);
                            var gtDate = searchValue.match(/^>(\\d{4}-\\d{2}-\\d{2})$/);
                            var ltDate = searchValue.match(/^<(\\d{4}-\\d{2}-\\d{2})$/);
                            if (rangeDate) {
                                conditions = [[fieldPath, ">=", rangeDate[1]], [fieldPath, "<=", rangeDate[2]]];
                            } else if (gtDate) {
                                conditions = [[fieldPath, ">", gtDate[1]]];
                            } else if (ltDate) {
                                conditions = [[fieldPath, "<", ltDate[1]]];
                            } else if (/^\\d{4}-\\d{2}-\\d{2}$/.test(searchValue)) {
                                conditions = [[fieldPath, "=", searchValue]];
                            } else {
                                conditions = [[fieldPath, "ilike", searchValue]];
                            }
                        }
                    }
                    break;
                }

                case "selection":
                    if (searchValue.includes(",")) {
                        const vals = searchValue.split(",").map(function (s) {
                            return s.trim();
                        }).filter(Boolean);
                        if (vals.length) conditions = [[fieldPath, "in", vals]];
                    } else {
                        conditions = [[fieldPath, "=", searchValue]];
                    }
                    break;

                case "boolean": {
                    const lower = searchValue.toLowerCase();
                    if (["true", "1", "yes", "y", "t"].includes(lower)) conditions = [[fieldPath, "=", true]];
                    else if (["false", "0", "no", "n", "f"].includes(lower)) conditions = [[fieldPath, "=", false]];
                    break;
                }

                case "many2one":
                case "many2many":
                case "one2many":
                    if (searchValue.includes(",")) {
                        const parts = searchValue.split(",").map(function (s) {
                            return s.trim();
                        }).filter(Boolean);
                        if (parts.length) conditions = [[fieldPath, "in", parts]];
                    } else {
                        conditions = [[fieldPath, "ilike", searchValue]];
                    }
                    break;

                default:
                    conditions = [[fieldPath, "ilike", searchValue]];
            }

            conditions.forEach(function (c) {
                domain.push(c);
            });
        }
        return domain;
    },

    get_filtered_records(list) {
        const records = list.records;
        const columnDomain = this._buildDomain();
        if (!this.isX2Many || !columnDomain.length) return records;

        return records.filter((record) => columnDomain.every((condition) => {
            const [fieldPath, operator] = condition;
            const fieldName = fieldPath.split(".")[0];
            const colInfo = this.columnInfoMap[fieldName];
            const context = {...record.evalContext};

            if (["many2one", "many2many", "one2many"].includes(colInfo?.type)) {
                const fieldValue = record.data[fieldName];
                let names = [];
                if (colInfo.type === "many2one") {
                    names = fieldValue ? [fieldValue[1]] : [];
                } else {
                    names = fieldValue?.records?.map((item) => item.data.display_name || item.data.name || "") || [];
                }
                context[fieldName] = {name: operator === "in" ? names : names.join(", ")};
            }
            return new Domain([condition]).contains(context);
        }));
    },

    _applyColumnFilters() {
        if (this.isX2Many) {
            this._searchRowInjected = false;
            this.render();
            return;
        }

        const columnDomain = this._buildDomain();
        const searchModel = this.env?.searchModel;
        if (searchModel) {
            searchModel.globalDomain = [
                ...this.baseGlobalDomain,
                ...columnDomain,
            ];
            searchModel._domain = null;
            searchModel._reloadSections().then(function () {
                if (searchModel._domain) searchModel._domain = null;
                searchModel.trigger("update");
            });
        }
    },

    async _fetchFieldInfo() {
        const resModel = this.props.list?.model?.config?.resModel;
        if (!resModel) return;
        const fieldNames = Object.keys(this.columnInfoMap);
        if (!fieldNames.length) return;
        try {
            const orm = this.env?.orm;
            if (!orm) return;
            const backendInfo = await orm.call("column.filter.field.info", "get_field_info_batch", [resModel, fieldNames]);
            let needsReinject = false;
            for (const [name, info] of Object.entries(backendInfo)) {
                const colInfo = this.columnInfoMap[name];
                if (colInfo && info.searchable) {
                    if (info.selection && JSON.stringify(info.selection) !== JSON.stringify(colInfo.selection)) {
                        colInfo.selection = info.selection;
                        needsReinject = true;
                    }
                    if (info.relation) colInfo.relation = info.relation;
                }
            }
            if (needsReinject) {
                const thead = this.rootRef?.el?.querySelector("thead");
                if (thead) {
                    const existingRow = thead.querySelector(".column_search_row");
                    if (existingRow) {
                        existingRow.remove();
                        this._searchRowInjected = false;
                        this._retryInject();
                    }
                }
            }
        } catch (e) {
            console.warn("CF fetch field info error:", e);
        }
    },
    _addCellQuickFilters(tbody) {
        tbody.querySelectorAll("td.o_data_cell[data-name]").forEach(function (td) {
            if (td.querySelector(".o_cf_quick")) return;
            const fieldName = td.getAttribute("data-name");
            if (!fieldName) return;

            const qf = document.createElement("span");
            qf.className = "o_cf_quick";
            qf.style.cssText = "display:none;position:absolute;bottom:0;right:0;gap:3px;background:#fff;border:1px solid #ddd;border-radius:3px;padding:1px 3px;z-index:10;font-size:10px;";

            const eq = document.createElement("a");
            eq.textContent = "=";
            eq.href = "#";
            eq.style.cssText = "cursor:pointer;padding:0 3px;color:#0d6efd;text-decoration:none;";
            eq.addEventListener("click", function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                const val = td.textContent.trim();
                this.columnFilters[fieldName] = val;
                this._applyColumnFilters();
            }.bind(this));

            const neq = document.createElement("a");
            neq.textContent = "!=";
            neq.href = "#";
            neq.style.cssText = "cursor:pointer;padding:0 3px;color:#dc3545;text-decoration:none;";
            neq.addEventListener("click", function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                this.columnFilters[fieldName] = "!=" + td.textContent.trim();
                this._applyColumnFilters();
            }.bind(this));

            qf.appendChild(eq);
            qf.appendChild(document.createTextNode("|"));
            qf.appendChild(neq);
            td.style.position = "relative";
            td.appendChild(qf);

            td.addEventListener("mouseenter", function () {
                qf.style.display = "inline-flex";
            });
            td.addEventListener("mouseleave", function () {
                qf.style.display = "none";
            });
        });
    },
});
