/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class PdaRecordDashboard extends Component {
    static template = "wd_qooling_app.PdaRecordDashboard";
    static props = { "*": true };
    static config = {};

    setup() {
        this.openRecord = this.openRecord.bind(this);
        this.createRecord = this.createRecord.bind(this);
        this.backToDashboard = this.backToDashboard.bind(this);
        this.applyFilters = this.applyFilters.bind(this);
        this.clearFilters = this.clearFilters.bind(this);
        this.toggleFilters = this.toggleFilters.bind(this);
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            records: [],
            loading: true,
            error: "",
            filterError: "",
            filtersExpanded: false,
            filters: { dateFrom: "", dateTo: "", number: "", status: "" },
        });
        onWillStart(() => this.loadRecords());
    }

    get dashboardConfig() {
        return this.constructor.config;
    }

    get statusOptions() {
        return this.dashboardConfig.statusOptions;
    }

    get hasActiveFilters() {
        const { dateFrom, dateTo, number, status } = this.state.filters;
        return Boolean(dateFrom || dateTo || number.trim() || status);
    }

    buildDomain() {
        const config = this.dashboardConfig;
        const { dateFrom, dateTo, number, status } = this.state.filters;
        const domain = [];
        const normalizedNumber = number.trim();
        if (dateFrom) {
            domain.push([config.dateField, ">=", config.dateType === "datetime"
                ? `${dateFrom} 00:00:00`
                : dateFrom]);
        }
        if (dateTo) {
            domain.push([config.dateField, "<=", config.dateType === "datetime"
                ? `${dateTo} 23:59:59`
                : dateTo]);
        }
        if (normalizedNumber) {
            domain.push(["name", "ilike", normalizedNumber]);
        }
        if (status) {
            domain.push(["state", "=", status]);
        }
        return domain;
    }

    async loadRecords() {
        const config = this.constructor.config;
        this.state.loading = true;
        this.state.error = "";
        let success = true;
        try {
            const records = await this.orm.searchRead(
                config.model,
                this.buildDomain(),
                config.fields,
                { order: "id desc", limit: 100 },
            );
            this.state.records = records.map((record) => ({
                ...record,
                dateValue: record[config.dateField] || "",
                referenceValue: config.referenceFields
                    .map((field) => record[field])
                    .find((value) => value) || "",
            }));
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Could not load PDA records.");
            success = false;
        } finally {
            this.state.loading = false;
        }
        return success;
    }

    async applyFilters() {
        this.state.filterError = "";
        if (this.state.filters.dateFrom && this.state.filters.dateTo
            && this.state.filters.dateFrom > this.state.filters.dateTo) {
            this.state.filterError = _t("From date cannot be later than To date.");
            return;
        }
        if (await this.loadRecords()) {
            this.state.filtersExpanded = false;
        }
    }

    async clearFilters() {
        this.state.filters.dateFrom = "";
        this.state.filters.dateTo = "";
        this.state.filters.number = "";
        this.state.filters.status = "";
        this.state.filterError = "";
        await this.loadRecords();
    }

    toggleFilters() {
        this.state.filtersExpanded = !this.state.filtersExpanded;
    }

    getStateLabel(state) {
        return this.statusOptions.find((option) => option.value === state)?.label || state;
    }

    openRecord(record) {
        return this.action.doAction(this.constructor.config.formAction, {
            additionalContext: { active_id: record.id },
        });
    }

    createRecord() {
        return this.action.doAction(this.constructor.config.formAction, {
            additionalContext: { new_record: true },
        });
    }

    backToDashboard() {
        return this.action.doAction("wd_qooling_app.action_qooling_dashboard");
    }
}

class InboundPdaRecordDashboard extends PdaRecordDashboard {
    static config = {
        title: _t("Inbound Record"),
        model: "wd.qooling.inbound.form",
        fields: ["name", "state", "date", "ref_no", "container_shipment_number"],
        dateField: "date",
        referenceFields: ["ref_no", "container_shipment_number"],
        dateType: "date",
        statusOptions: [
            { value: "draft", label: _t("Draft") },
            { value: "submitted", label: _t("Submitted") },
        ],
        formAction: "wd_qooling_app.action_qooling_inbound_pda_form",
    };
}

class OutboundPdaRecordDashboard extends PdaRecordDashboard {
    static config = {
        title: _t("Outbound Record"),
        model: "wd.qooling.outbound.form",
        fields: ["name", "state", "date_arrival", "ref_no", "mrn_number"],
        dateField: "date_arrival",
        referenceFields: ["ref_no", "mrn_number"],
        dateType: "datetime",
        statusOptions: [
            { value: "draft", label: _t("Draft") },
            { value: "submitted", label: _t("Submitted") },
            { value: "exception_pending", label: _t("Exception pending") },
            { value: "closed", label: _t("Closed") },
        ],
        formAction: "wd_qooling_app.action_qooling_outbound_pda_form",
    };
}

class TemperaturePdaRecordDashboard extends PdaRecordDashboard {
    static config = {
        title: _t("Temperature Record"),
        model: "wd.qooling.temperature.record",
        fields: ["name", "state", "date", "customer", "container_number"],
        dateField: "date",
        referenceFields: ["customer", "container_number"],
        dateType: "datetime",
        statusOptions: [
            { value: "draft", label: _t("Draft") },
            { value: "submitted", label: _t("Submitted") },
            { value: "exception_pending", label: _t("Exception pending") },
            { value: "closed", label: _t("Closed") },
        ],
        formAction: "wd_qooling_app.action_qooling_temperature_pda_form",
    };
}

registry.category("actions").add("wd_qooling_inbound_pda_dashboard", InboundPdaRecordDashboard);
registry.category("actions").add("wd_qooling_outbound_pda_dashboard", OutboundPdaRecordDashboard);
registry.category("actions").add("wd_qooling_temperature_pda_dashboard", TemperaturePdaRecordDashboard);
