import { RPCError } from "@web/core/network/rpc";
import { Domain, InvalidDomainError } from "@web/core/domain";

export const DISPLAY_FIELD_TYPES = new Set([
    "char",
    "text",
    "many2one",
    "selection",
    "boolean",
    "integer",
    "float",
    "monetary",
    "date",
    "datetime",
]);

export const FILTER_FIELD_TYPES = new Set([
    "char",
    "text",
    "many2one",
    "selection",
    "boolean",
    "integer",
    "float",
    "date",
    "datetime",
]);

export class ProfileResolutionError extends Error {
    constructor(code, message) {
        super(message);
        this.name = "ProfileResolutionError";
        this.code = code;
    }
}

function profileError(code, message) {
    return new ProfileResolutionError(code, message);
}

export async function resolvePickerProfile(orm, code, relation) {
    const profiles = await orm.searchRead(
        "advanced.record.picker.profile",
        [["code", "=", code]],
        ["id", "code", "model_id", "active", "domain", "default_order", "page_size"]
    );
    if (!profiles.length) {
        throw profileError("PROFILE_NOT_FOUND", `Picker Profile "${code}" was not found.`);
    }

    const profile = profiles[0];
    if (!profile.active) {
        throw profileError("PROFILE_INACTIVE", `Picker Profile "${code}" is inactive.`);
    }

    const [model] = await orm.read("ir.model", [profile.model_id[0]], ["model"]);
    if (!model || model.model !== relation) {
        throw profileError(
            "PROFILE_MODEL_MISMATCH",
            `Picker Profile "${code}" does not target the field relation.`
        );
    }

    const columns = await orm.searchRead(
        "advanced.record.picker.column",
        [["profile_id", "=", profile.id]],
        ["id", "field_id", "sequence", "visible", "filterable"]
    );
    const fieldIds = columns.map((column) => column.field_id?.[0]).filter(Boolean);
    const fieldRecords = fieldIds.length
        ? await orm.read(
              "ir.model.fields",
              fieldIds,
              ["name", "model", "ttype", "relation", "field_description"]
          )
        : [];
    const fieldsById = new Map(
        fieldRecords.map((field) => [
            field.id,
            { ...field, string: field.field_description },
        ])
    );

    const resolvedColumns = columns.map((column) => {
        const field = fieldsById.get(column.field_id?.[0]);
        if (
            !field ||
            field.model !== relation ||
            !DISPLAY_FIELD_TYPES.has(field.ttype) ||
            !column.visible ||
            (column.filterable && !FILTER_FIELD_TYPES.has(field.ttype))
        ) {
            throw profileError(
                "INVALID_PROFILE_CONFIGURATION",
                `Picker Profile "${code}" contains an invalid column.`
            );
        }
        return { ...column, field };
    });

    if (!resolvedColumns.length) {
        throw profileError(
            "INVALID_PROFILE_CONFIGURATION",
            `Picker Profile "${code}" has no valid display columns.`
        );
    }

    let profileDomain;
    try {
        profileDomain = new Domain(profile.domain || "[]").toList();
    } catch (error) {
        if (error instanceof InvalidDomainError) {
            throw profileError(
                "INVALID_PROFILE_CONFIGURATION",
                `Picker Profile "${code}" contains an invalid domain.`
            );
        }
        throw error;
    }

    return Object.freeze({
        id: profile.id,
        code: profile.code,
        modelId: profile.model_id[0],
        relation,
        active: profile.active,
        domain: Object.freeze(profileDomain),
        defaultOrder: profile.default_order || "",
        pageSize: profile.page_size,
        columns: Object.freeze(resolvedColumns.map((column) => Object.freeze(column))),
    });
}

export function isProfileResolutionError(error) {
    return error instanceof ProfileResolutionError;
}

export function isRpcError(error) {
    return error instanceof RPCError;
}
