import { _t } from "@web/core/l10n/translation";
import { Domain } from "@web/core/domain";
import { parseDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { getFieldContext, getFieldDomain } from "@web/model/relational_model/utils";
import { Dialog } from "@web/core/dialog/dialog";
import {
    Many2OneField,
    many2OneField,
    m2oTupleFromData,
} from "@web/views/fields/many2one/many2one_field";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";
import { View } from "@web/views/view";
import { escape } from "@web/core/utils/strings";
import {
    isProfileResolutionError,
    isRpcError,
    resolvePickerProfile,
} from "./profile_resolver";

export function makeCandidateDomain(originalDomain, profileDomain, temporaryDomain) {
    return Domain.and([originalDomain, profileDomain, temporaryDomain]).toList();
}

export function makeRevalidationDomain(originalDomain, profileDomain, selectedId) {
    return Domain.and([originalDomain, profileDomain, [["id", "=", selectedId]]]).toList();
}

export function serializeDatetimeFilter(value) {
    const datetime = parseDateTime(value, { format: "yyyy-MM-dd'T'HH:mm" });
    return datetime ? serializeDateTime(datetime) : "";
}

export function makeCandidateListArch(profile, candidateFields = {}) {
    const attributes = [
        'create="0"',
        'edit="0"',
        'delete="0"',
        `limit="${profile.pageSize || 80}"`,
    ];
    if (profile.defaultOrder) {
        attributes.push(`default_order="${escape(profile.defaultOrder)}"`);
    }
    const displayFields = profile.columns
        .filter((column) => column.visible)
        .map((column) => `<field name="${escape(column.field.name)}"/>`)
        .join("");
    const displayFieldNames = new Set(
        profile.columns.map((column) => column.field.name)
    );
    const dependencyFields = profile.columns
        .map((column) => candidateFields[column.field.name]?.currency_field)
        .filter((fieldName) => fieldName && !displayFieldNames.has(fieldName))
        .map((fieldName) => `<field name="${escape(fieldName)}" column_invisible="True"/>`)
        .join("");
    return `<list ${attributes.join(" ")}>${displayFields}${dependencyFields}</list>`;
}

export class AdvancedRecordPickerDialog extends Component {
    static template = "wd_web_advanced_record_picker.AdvancedRecordPickerDialog";
    static components = { Dialog, Many2XAutocomplete, View };
    static props = {
        profile: { type: Object, required: true },
        arch: { type: String, required: true },
        fields: { type: Object, required: true },
        context: { type: Object, required: true },
        getOriginalDomain: { type: Function, required: true },
        onSelected: { type: Function, required: true },
        close: { type: Function, required: true },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            filters: {},
            filterDisplayValues: {},
            reloadKey: 0,
            selecting: false,
        });
    }

    get displayColumns() {
        return this.props.profile.columns.filter((column) => column.visible);
    }

    get filterColumns() {
        return this.displayColumns.filter((column) => column.filterable);
    }

    get modelName() {
        return this.props.profile.relation;
    }

    get temporaryDomain() {
        const domain = [];
        for (const [fieldName, rawValue] of Object.entries(this.state.filters || {})) {
            if (rawValue === "" || rawValue === null || rawValue === undefined) {
                continue;
            }
            const column = this.displayColumns.find((item) => item.field.name === fieldName);
            if (!column || !column.filterable) {
                continue;
            }
            const type = column.field.ttype;
            if (["char", "text"].includes(type)) {
                domain.push([fieldName, "ilike", rawValue]);
            } else if (type === "many2one") {
                const selectedId = Number(rawValue);
                if (!Number.isNaN(selectedId) && selectedId > 0) {
                    domain.push([fieldName, "=", selectedId]);
                }
            } else if (["integer", "float"].includes(type)) {
                const numberValue = Number(rawValue);
                if (!Number.isNaN(numberValue)) {
                    domain.push([fieldName, "=", numberValue]);
                }
            } else if (type === "datetime") {
                const serializedValue = serializeDatetimeFilter(rawValue);
                if (serializedValue) {
                    domain.push([fieldName, "=", serializedValue]);
                }
            } else if (["selection", "boolean", "date"].includes(type)) {
                domain.push([fieldName, "=", rawValue]);
            }
        }
        return domain;
    }

    get effectiveDomain() {
        return makeCandidateDomain(
            this.props.getOriginalDomain(),
            this.props.profile.domain,
            this.temporaryDomain
        );
    }

    get viewProps() {
        return {
            allowSelectors: false,
            arch: this.props.arch,
            context: this.props.context,
            display: { searchPanel: false },
            domain: this.effectiveDomain,
            editable: false,
            fields: this.props.fields,
            limit: this.props.profile.pageSize || 80,
            loadIrFilters: false,
            noBreadcrumbs: true,
            relatedModels: {
                [this.modelName]: { fields: this.props.fields },
            },
            resModel: this.modelName,
            searchMenuTypes: [],
            selectRecord: (resId) => this.onSelect(resId),
            showButtons: false,
            type: "list",
        };
    }

    filterValue(fieldName) {
        return this.state.filters[fieldName] || "";
    }

    fieldDefinition(column) {
        return this.props.fields[column.field.name];
    }

    many2oneFilterProps(column) {
        const field = this.fieldDefinition(column);
        return {
            activeActions: { create: false, createEdit: false, write: false },
            autoSelect: true,
            context: this.props.context,
            fieldString: field.string,
            getDomain: () => [],
            resModel: field.relation,
            update: (records) => this.onMany2oneFilterUpdate(column.field.name, records),
            value: this.state.filterDisplayValues[column.field.name] || "",
        };
    }

    setFilter(fieldName, value) {
        this.state.filters = { ...this.state.filters, [fieldName]: value };
    }

    onFilterInput(event) {
        const fieldName = event.target.dataset.column;
        this.setFilter(fieldName, event.target.value);
    }

    onBooleanFilterInput(event) {
        const value = event.target.value;
        this.setFilter(
            event.target.dataset.column,
            value === "" ? "" : value === "true"
        );
    }

    async onMany2oneFilterUpdate(fieldName, records) {
        const record = records?.[0];
        let displayName = record?.display_name || record?.name || "";
        if (record?.id && !displayName) {
            const [resolvedRecord] = await this.orm.read(
                this.fieldDefinition(
                    this.displayColumns.find((column) => column.field.name === fieldName)
                ).relation,
                [record.id],
                ["display_name"]
            );
            displayName = resolvedRecord?.display_name || "";
        }
        this.state.filterDisplayValues = {
            ...this.state.filterDisplayValues,
            [fieldName]: displayName,
        };
        this.setFilter(fieldName, record?.id || "");
    }

    async onSelect(selectedId) {
        if (!selectedId || this.state.selecting) {
            return;
        }
        this.state.selecting = true;
        try {
            if (await this.props.onSelected(selectedId)) {
                this.props.close();
            } else {
                this.state.reloadKey++;
            }
        } finally {
            this.state.selecting = false;
        }
    }

    onClose() {
        this.props.close();
    }
}

export class AdvancedRecordPickerField extends Many2OneField {
    static template = "wd_web_advanced_record_picker.AdvancedRecordPickerField";
    static components = { Many2OneField };
    static props = {
        ...Many2OneField.props,
        pickerProfile: { type: String, optional: true },
    };

    setup() {
        super.setup();
        this.addDialog = useOwnedDialogs();
        this.fieldService = useService("field");
        this.notification = useService("notification");
        this.profileState = useState({
            arch: null,
            candidateFields: null,
            profile: null,
            error: null,
        });
        onWillStart(async () => {
            const code = this.props.pickerProfile?.trim();
            if (!code) {
                return;
            }
            try {
                this.profileState.profile = await resolvePickerProfile(this.orm, code, this.relation);
                const fieldNames = this.profileState.profile.columns.map(
                    (column) => column.field.name
                );
                let candidateFields = await this.fieldService.loadFields(
                    this.relation,
                    { fieldNames }
                );
                const dependencyFieldNames = fieldNames
                    .map((fieldName) => candidateFields[fieldName]?.currency_field)
                    .filter((fieldName) => fieldName && !fieldNames.includes(fieldName));
                if (dependencyFieldNames.length) {
                    candidateFields = await this.fieldService.loadFields(this.relation, {
                        fieldNames: [...fieldNames, ...new Set(dependencyFieldNames)],
                    });
                }
                this.profileState.candidateFields = candidateFields;
                this.profileState.arch = makeCandidateListArch(
                    this.profileState.profile,
                    candidateFields
                );
            } catch (error) {
                console.error("ARP_PROFILE_DEBUG", error);
                if (isProfileResolutionError(error)) {
                    this.profileState.error = error;
                } else if (isRpcError(error)) {
                    this.profileState.error = error;
                    this.notification.add(_t("Advanced Record Picker is unavailable."), {
                        type: "warning",
                    });
                } else {
                    throw error;
                }
            }
        });
    }

    get nativeProps() {
        const { pickerProfile, ...nativeProps } = this.props;
        return nativeProps;
    }

    get canOpenAdvancedPicker() {
        return (
            !this.props.readonly &&
            Boolean(
                this.profileState.profile &&
                    this.profileState.arch &&
                    this.profileState.candidateFields
            )
        );
    }

    get candidateContext() {
        return getFieldContext(
            this.props.record,
            this.props.name,
            this.props.context
        );
    }

    get originalDomain() {
        return getFieldDomain(
            this.props.record,
            this.props.name,
            this.props.domain
        );
    }

    async selectAdvancedRecord(selectedId) {
        const matches = await this.orm.searchRead(
            this.relation,
            makeRevalidationDomain(
                this.originalDomain,
                this.profileState.profile.domain,
                selectedId
            ),
            ["id", "display_name"],
            { context: this.candidateContext, limit: 1 }
        );
        if (!matches.length) {
            this.notification.add(_t("Selected record is no longer valid."), {
                type: "warning",
            });
            return false;
        }
        await this.updateRecord(m2oTupleFromData(matches[0]));
        return true;
    }

    openAdvancedPicker() {
        if (!this.canOpenAdvancedPicker) {
            return;
        }
        this.addDialog(AdvancedRecordPickerDialog, {
            profile: this.profileState.profile,
            arch: this.profileState.arch,
            fields: this.profileState.candidateFields,
            context: this.candidateContext,
            getOriginalDomain: () => this.originalDomain,
            onSelected: (selectedId) => this.selectAdvancedRecord(selectedId),
        });
    }
}

export const advancedRecordPickerField = {
    ...many2OneField,
    component: AdvancedRecordPickerField,
    displayName: _t("Advanced Record Picker"),
    extractProps({ attrs, context, decorations, options, string }, dynamicInfo) {
        return {
            ...many2OneField.extractProps({ attrs, context, decorations, options, string }, dynamicInfo),
            pickerProfile:
                typeof options.picker_profile === "string" ? options.picker_profile.trim() : "",
        };
    },
};

registry.category("fields").add("advanced_record_picker", advancedRecordPickerField);
