/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const HEADER_FIELDS = [
    ["supplier_id", "Supplier"],
    ["invoice_number", "Invoice number"],
    ["invoice_date", "Invoice date"],
    ["currency_id", "Currency"],
    ["total_amount", "Total amount"],
    ["total_tax", "Total tax"],
];
const LINE_FIELDS = [
    ["product_id", "Product"],
    ["description", "Description"],
    ["quantity", "Quantity"],
    ["unit_price", "Unit price"],
    ["subtotal", "Subtotal"],
    ["tax_ids", "Taxes"],
    ["tax_amount", "Tax amount"],
    ["line_total_amount", "Line total"],
];

export class VendorInvoiceReviewDialog extends Component {
    static template = "ai_vendor_invoice.VendorInvoiceReviewDialog";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            result: structuredClone(
                this.props.record.data.human_review_result || { header: {}, lines: [] }
            ),
            edited: {},
            thresholds: { global: 0.7, critical: 0.9 },
        });
        onWillStart(async () => {
            const configs = await this.props.record.model.orm.searchRead(
                "wd.confidence.threshold",
                [],
                ["global_threshold", "critical_threshold"],
                { limit: 1 },
            );
            if (configs.length) {
                this.state.thresholds = {
                    global: configs[0].global_threshold,
                    critical: configs[0].critical_threshold,
                };
            }
        });
    }

    get headerFields() {
        return HEADER_FIELDS;
    }

    get lineFields() {
        return LINE_FIELDS;
    }

    get candidateResult() {
        const relation = this.props.record.data.parse_attempt_ids;
        const attempts = relation?.records || [];
        const current = attempts.find(
            (attempt) =>
                attempt.data.id === this.props.record.data.current_parse_attempt_id?.[0]
        );
        return current?.data.canonical_result || null;
    }

    fieldValue(field) {
        return this.state.result.header?.[field] ?? "";
    }

    lineValue(line, field) {
        const value = line[field];
        return Array.isArray(value) ? value.join(",") : value ?? "";
    }

    setHeader(field, value) {
        this.state.result.header ||= {};
        this.state.result.header[field] = value;
        this.state.edited[`header.${field}`] = true;
    }

    setLine(index, field, value) {
        this.state.result.lines[index][field] = field === "tax_ids"
            ? value.split(",").map((tax) => Number(tax.trim())).filter(Boolean)
            : value;
        this.state.edited[`line.${index}.${field}`] = true;
    }

    applyCandidate() {
        const candidate = this.candidateResult;
        if (!candidate) {
            return;
        }
        const candidateHeader = candidate.header || {};
        this.state.result.header ||= {};
        for (const [field] of HEADER_FIELDS) {
            if (!this.state.edited[`header.${field}`] && candidateHeader[field]) {
                this.state.result.header[field] = candidateHeader[field].value;
            }
        }
        for (const [index, candidateLine] of (candidate.lines || []).entries()) {
            this.state.result.lines[index] ||= {};
            for (const [field] of LINE_FIELDS) {
                if (!this.state.edited[`line.${index}.${field}`] && candidateLine[field]) {
                    this.state.result.lines[index][field] = candidateLine[field].value;
                }
            }
        }
    }

    confidenceClass(field, line = null) {
        const source = line ? line[field] : this.candidateResult?.header?.[field];
        const confidence = source?.confidence;
        if (confidence === undefined) {
            return "";
        }
        const critical = ["invoice_number", "invoice_date", "total_amount"].includes(field);
        if (confidence < (critical ? this.state.thresholds.critical : this.state.thresholds.global)) {
            return critical ? "o_vendor_invoice_confidence_critical" : "o_vendor_invoice_confidence_low";
        }
        return "";
    }

    async confirm() {
        await this.props.record.model.orm.call(
            "vendor.invoice.import.task",
            "action_confirm_statement",
            [[this.props.record.resId], this.state.result],
        );
        await this.props.record.load();
    }
}

registry.category("fields").add("vendor_invoice_review", {
    component: VendorInvoiceReviewDialog,
});
