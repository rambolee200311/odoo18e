import { describe, expect, test } from "@odoo/hoot";
import { click, edit, queryValue, waitFor, waitUntil } from "@odoo/hoot-dom";
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";
import "@wd_web_advanced_record_picker/fields/advanced_record_picker_field";
import {
    makeCandidateDomain,
    makeCandidateListArch,
    makeRevalidationDomain,
    serializeDatetimeFilter,
} from "@wd_web_advanced_record_picker/fields/advanced_record_picker_field";
import {
    DISPLAY_FIELD_TYPES,
    FILTER_FIELD_TYPES,
    isProfileResolutionError,
    resolvePickerProfile,
} from "@wd_web_advanced_record_picker/fields/profile_resolver";

class Partner extends models.Model {
    active = fields.Boolean({ default: true });
    category = fields.Selection({
        selection: [
            ["customer", "Customer"],
            ["supplier", "Supplier"],
        ],
    });
    joined_on = fields.Date();
    last_seen = fields.Datetime();
    name = fields.Char();
    parent_id = fields.Many2one({ relation: "partner" });
    rank = fields.Integer();
    _records = [
        {
            id: 1,
            active: true,
            category: "customer",
            joined_on: "2026-01-01",
            last_seen: "2026-03-04 12:30:00",
            name: "Test Partner",
            rank: 1,
        },
        {
            id: 2,
            active: true,
            category: "supplier",
            joined_on: "2026-02-01",
            last_seen: "2026-03-05 12:30:00",
            name: "Acme",
            parent_id: 1,
            rank: 2,
        },
    ];
}

class PickerHost extends models.Model {
    partner_id = fields.Many2one({ relation: "partner", string: "Partner" });
    _records = [{ id: 1, partner_id: 1 }];
    _onChanges = { partner_id() {} };
}

class PickerWizard extends models.Model {
    partner_id = fields.Many2one({ relation: "partner", string: "Partner" });
    _onChanges = { partner_id() {} };
}

class ResUsers extends models.Model {
    _name = "res.users";

    name = fields.Char();
    _records = [{ id: 2, name: "Administrator" }];
}

defineModels([Partner, PickerHost, PickerWizard, ResUsers]);

function makeOrm({ profiles = [], model = { id: 11, model: "res.partner" }, columns = [], fields = [] } = {}) {
    const calls = [];
    return {
        calls,
        async searchRead(modelName, domain, fieldNames) {
            calls.push(["searchRead", modelName, domain, fieldNames]);
            if (modelName.endsWith(".profile")) {
                return profiles;
            }

            return columns;
        },
        async read(modelName, ids, fieldNames) {
            calls.push(["read", modelName, ids, fieldNames]);
            if (modelName === "ir.model") {
                return [model];
            }
            return fields;
        },
    };
}

function mockPartnerProfile({
    code = "partner_picker",
    domain = "[('active', '=', True)]",
    pageSize = 80,
    columns = [
        {
            id: 21,
            name: "name",
            string: "Name",
            ttype: "char",
            filterable: true,
        },
    ],
} = {}) {
    onRpc("advanced.record.picker.profile", "search_read", () => [
        {
            id: 1,
            code,
            model_id: [11, "Partner"],
            active: true,
            domain,
            default_order: "name asc",
            page_size: pageSize,
        },
    ]);
    onRpc("ir.model", "read", () => [{ id: 11, model: "partner" }]);
    onRpc("advanced.record.picker.column", "search_read", () =>
        columns.map((column, index) => ({
            id: index + 1,
            field_id: [column.id, column.string],
            sequence: (index + 1) * 10,
            visible: true,
            filterable: column.filterable,
        }))
    );
    onRpc("ir.model.fields", "read", () =>
        columns.map((column) => ({
            id: column.id,
            model: "partner",
            name: column.name,
            relation: column.relation,
            field_description: column.string,
            ttype: column.ttype,
        }))
    );
}

describe("profile resolver", () => {
    test("uses standard ORM reads and returns a frozen runtime definition", async () => {
        const orm = makeOrm({
            profiles: [
                {
                    id: 1,
                    code: "partner_picker",
                    model_id: [11, "Contact"],
                    active: true,
                    domain: "[('active', '=', True)]",
                    default_order: "name asc",
                    page_size: 80,
                },
            ],
            columns: [
                { id: 2, field_id: [21, "Name"], sequence: 10, visible: true, filterable: true },
            ],
            fields: [
                {
                    id: 21,
                    name: "name",
                    model: "res.partner",
                    ttype: "char",
                    field_description: "Name",
                },
            ],
        });

        const profile = await resolvePickerProfile(orm, "partner_picker", "res.partner");

        expect(profile.code).toBe("partner_picker");
        expect(profile.columns[0].field.name).toBe("name");
        expect(profile.columns[0].field.string).toBe("Name");
        expect(profile.domain).toEqual([["active", "=", true]]);
        expect(Object.isFrozen(profile)).toBe(true);
        expect(orm.calls.map(([method, model]) => `${method}:${model}`)).toEqual([
            "searchRead:advanced.record.picker.profile",
            "read:ir.model",
            "searchRead:advanced.record.picker.column",
            "read:ir.model.fields",
        ]);
        expect(orm.calls[3][3]).toEqual([
            "name",
            "model",
            "ttype",
            "relation",
            "field_description",
        ]);
    });

    test("reports missing profiles as an expected configuration error", async () => {
        const error = await resolvePickerProfile(makeOrm(), "missing", "res.partner").catch(
            (caught) => caught
        );

        expect(isProfileResolutionError(error)).toBe(true);
        expect(error.code).toBe("PROFILE_NOT_FOUND");
    });

    test("rejects invalid column metadata", async () => {
        const orm = makeOrm({
            profiles: [
                {
                    id: 1,
                    code: "partner_picker",
                    model_id: [11, "Contact"],
                    active: true,
                    domain: "[]",
                    page_size: 80,
                },
            ],
            columns: [
                { id: 2, field_id: [21, "Binary"], sequence: 10, visible: true, filterable: false },
            ],
            fields: [
                {
                    id: 21,
                    name: "image",
                    model: "res.partner",
                    ttype: "binary",
                    field_description: "Image",
                },
            ],
        });

        const error = await resolvePickerProfile(orm, "partner_picker", "res.partner").catch(
            (caught) => caught
        );

        expect(error.code).toBe("INVALID_PROFILE_CONFIGURATION");
    });
});

test("filterable field types remain a subset of display field types", () => {
    expect([...FILTER_FIELD_TYPES].every((type) => DISPLAY_FIELD_TYPES.has(type))).toBe(true);
});

test("serializes datetime-local filters through the Odoo timezone helpers", () => {
    expect(serializeDatetimeFilter("2026-03-04T12:30")).toMatch(
        /^\d{4}-\d{2}-\d{2} \d{2}:30:00$/
    );
});

test("combines profile domain in candidate and revalidation domains", () => {
    const originalDomain = [["company_id", "=", 1]];
    const profileDomain = [["active", "=", true]];
    const temporaryDomain = [["name", "ilike", "acme"]];

    expect(makeCandidateDomain(originalDomain, profileDomain, temporaryDomain)).toEqual([
        "&",
        ["company_id", "=", 1],
        "&",
        ["active", "=", true],
        ["name", "ilike", "acme"],
    ]);
    expect(makeRevalidationDomain(originalDomain, profileDomain, 7)).toEqual([
        "&",
        ["company_id", "=", 1],
        "&",
        ["active", "=", true],
        ["id", "=", 7],
    ]);
});

test("builds a minimal native list arch with required monetary metadata", () => {
    const arch = makeCandidateListArch(
        {
            columns: [
                { visible: true, field: { name: "amount" } },
                { visible: true, field: { name: "name" } },
            ],
            defaultOrder: "name asc",
            pageSize: 30,
        },
        {
            amount: { currency_field: "currency_id" },
            name: {},
        }
    );

    expect(arch).toBe(
        '<list create="0" edit="0" delete="0" limit="30" default_order="name asc">' +
            '<field name="amount"/><field name="name"/>' +
            '<field name="currency_id" column_invisible="True"/></list>'
    );
});

test("renders a native many2one with an available advanced entry", async () => {
    const candidateDomains = [];
    const revalidationDomains = [];
    onRpc("res.users", "has_group", () => false);
    onRpc("partner", "web_search_read", ({ kwargs, parent }) => {
        candidateDomains.push(kwargs.domain);
        expect(kwargs.context.picker_flag).toBe(1);
        return parent();
    });
    onRpc("partner", "search_read", ({ kwargs, parent }) => {
        revalidationDomains.push(kwargs.domain);
        return parent();
    });
    mockPartnerProfile();
    await mountView({
        type: "form",
        resModel: "picker.host",
        resId: 1,
        arch: `
            <form>
                <field name="partner_id" widget="advanced_record_picker"
                    context="{'picker_flag': 1}"
                    options="{'picker_profile': 'partner_picker'}"/>
            </form>`,
    });

    expect(".o_field_widget.o_field_advanced_record_picker").toHaveCount(1);
    expect(".o_field_widget.o_field_advanced_record_picker button.oi-search").toHaveCount(1);
    await click(".o_field_widget.o_field_advanced_record_picker button.oi-search");
    await waitFor(".o_advanced_record_picker_dialog");
    expect(".o_advanced_record_picker_dialog .o_data_row").toHaveCount(2);
    expect(".o_advanced_record_picker_dialog th").toHaveText(/Name/);
    expect(".o_advanced_record_picker_dialog .o_pager").toHaveCount(1);
    expect(candidateDomains.at(-1)).toEqual([["active", "=", true]]);

    await click(".o_advanced_record_picker_dialog .o_data_row:first-child td[name='name']");
    await waitUntil(
        () =>
            queryValue(".o_field_widget.o_field_advanced_record_picker input") ===
            "Acme",
        { timeout: 1000 }
    );
    await waitUntil(
        () => document.querySelector(".o_form_editable")?.classList.contains("o_form_dirty"),
        { timeout: 1000 }
    );
    expect(".o_advanced_record_picker_dialog").toHaveCount(0);
    expect(".o_field_widget.o_field_advanced_record_picker input").toHaveValue("Acme");
    expect(".o_form_editable").toHaveClass("o_form_dirty");
    expect(revalidationDomains).toEqual([
        ["&", ["active", "=", true], ["id", "=", 2]],
    ]);
});

test("renders typed filters and reloads the native list server-side", async () => {
    const candidateDomains = [];
    let revalidationDomain;
    onRpc("res.users", "has_group", () => false);
    onRpc("partner", "web_search_read", ({ kwargs, parent }) => {
        candidateDomains.push(kwargs.domain);
        return parent();
    });
    onRpc("partner", "search_read", ({ kwargs, parent }) => {
        revalidationDomain = kwargs.domain;
        return parent();
    });
    mockPartnerProfile({
        domain: "[]",
        columns: [
            { id: 21, name: "name", string: "Name", ttype: "char", filterable: true },
            { id: 22, name: "active", string: "Active", ttype: "boolean", filterable: true },
            {
                id: 23,
                name: "category",
                string: "Category",
                ttype: "selection",
                filterable: true,
            },
            { id: 24, name: "rank", string: "Rank", ttype: "integer", filterable: true },
            {
                id: 25,
                name: "joined_on",
                string: "Joined On",
                ttype: "date",
                filterable: true,
            },
            {
                id: 26,
                name: "parent_id",
                relation: "partner",
                string: "Parent",
                ttype: "many2one",
                filterable: true,
            },
            {
                id: 27,
                name: "last_seen",
                string: "Last Seen",
                ttype: "datetime",
                filterable: true,
            },
        ],
    });

    await mountView({
        type: "form",
        resModel: "picker.host",
        resId: 1,
        arch: `
            <form>
                <field name="partner_id" widget="advanced_record_picker"
                    options="{'picker_profile': 'partner_picker'}"/>
            </form>`,
    });
    await click(".o_field_widget.o_field_advanced_record_picker button.oi-search");
    await waitFor(".o_advanced_record_picker_dialog .o_data_row");

    expect("input[data-column='name'][type='text']").toHaveCount(1);
    expect("select[data-column='active']").toHaveCount(1);
    expect("select[data-column='category']").toHaveCount(1);
    expect("input[data-column='rank'][type='number']").toHaveCount(1);
    expect("input[data-column='joined_on'][type='date']").toHaveCount(1);
    expect("input[data-column='last_seen'][type='datetime-local']").toHaveCount(1);
    expect(".o_advanced_record_picker_dialog .o-autocomplete").toHaveCount(1);

    await click("input[data-column='name']");
    await edit("Acme");
    await waitUntil(
        () =>
            JSON.stringify(candidateDomains.at(-1)) ===
            JSON.stringify([["name", "ilike", "Acme"]])
    );
    expect(candidateDomains.at(-1)).toEqual([["name", "ilike", "Acme"]]);

    await edit("");
    await click("input[data-column='rank']");
    await edit("2");
    await waitUntil(
        () =>
            JSON.stringify(candidateDomains.at(-1)) ===
            JSON.stringify([["rank", "=", 2]])
    );
    expect(candidateDomains.at(-1)).toEqual([["rank", "=", 2]]);

    await edit("");
    const datetimeInput = document.querySelector("input[data-column='last_seen']");
    datetimeInput.value = "2026-03-04T12:30";
    datetimeInput.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await waitUntil(() => candidateDomains.at(-1)?.[0]?.[0] === "last_seen");
    expect(datetimeInput.value).toBe("2026-03-04T12:30");
    expect(candidateDomains.at(-1)[0][2]).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:30:00$/);

    datetimeInput.value = "";
    datetimeInput.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await waitUntil(() => candidateDomains.at(-1).length === 0);
    await waitFor(".o_advanced_record_picker_dialog .o_data_row");
    await click(".o_advanced_record_picker_dialog .o_data_row:first-child td[name='name']");
    await waitUntil(
        () =>
            queryValue(".o_field_widget.o_field_advanced_record_picker input") ===
            "Acme",
        { timeout: 1000 }
    );
    expect(revalidationDomain).toEqual([["id", "=", 2]]);
});

test("uses native paging and sorting with the configured page size", async () => {
    const requests = [];
    onRpc("res.users", "has_group", () => false);
    onRpc("partner", "web_search_read", ({ kwargs, parent }) => {
        requests.push({
            limit: kwargs.limit,
            offset: kwargs.offset,
            order: kwargs.order,
        });
        return parent();
    });
    mockPartnerProfile({ domain: "[]", pageSize: 1 });

    await mountView({
        type: "form",
        resModel: "picker.host",
        resId: 1,
        arch: `
            <form>
                <field name="partner_id" widget="advanced_record_picker"
                    options="{'picker_profile': 'partner_picker'}"/>
            </form>`,
    });
    await click(".o_field_widget.o_field_advanced_record_picker button.oi-search");
    await waitFor(".o_advanced_record_picker_dialog .o_data_row");
    expect(requests.at(-1).limit).toBe(1);
    expect(requests.at(-1).offset).toBe(0);

    await click(".o_advanced_record_picker_dialog .o_pager_next");
    await waitUntil(() => requests.at(-1).offset === 1, { timeout: 1000 });

    await click(".o_advanced_record_picker_dialog th.o_column_sortable[data-name='name']");
    await waitUntil(
        () => requests.at(-1).order?.toLowerCase().includes("desc"),
        { timeout: 1000 }
    );
});

test("keeps the dialog open when selection revalidation fails", async () => {
    let candidateLoads = 0;
    onRpc("res.users", "has_group", () => false);
    onRpc("partner", "web_search_read", ({ parent }) => {
        candidateLoads++;
        return parent();
    });
    onRpc("partner", "search_read", () => []);
    mockPartnerProfile();

    await mountView({
        type: "form",
        resModel: "picker.host",
        resId: 1,
        arch: `
            <form>
                <field name="partner_id" widget="advanced_record_picker"
                    options="{'picker_profile': 'partner_picker'}"/>
            </form>`,
    });
    await click(".o_field_widget.o_field_advanced_record_picker button.oi-search");
    await waitFor(".o_advanced_record_picker_dialog .o_data_row");
    const initialLoads = candidateLoads;
    await click(".o_advanced_record_picker_dialog .o_data_row:first-child td[name='name']");
    await waitUntil(() => candidateLoads > initialLoads, { timeout: 1000 });

    expect(".o_advanced_record_picker_dialog").toHaveCount(1);
    expect(".o_field_widget.o_field_advanced_record_picker input").toHaveValue("Test Partner");
    expect(candidateLoads).toBeGreaterThan(initialLoads);
});

test("updates a transient wizard record through the standard field path", async () => {
    onRpc("res.users", "has_group", () => false);
    mockPartnerProfile();

    await mountView({
        type: "form",
        resModel: "picker.wizard",
        arch: `
            <form>
                <field name="partner_id" widget="advanced_record_picker"
                    options="{'picker_profile': 'partner_picker'}"/>
            </form>`,
    });
    await click(".o_field_widget.o_field_advanced_record_picker button.oi-search");
    await waitFor(".o_advanced_record_picker_dialog .o_data_row");
    await click(".o_advanced_record_picker_dialog .o_data_row:first-child td[name='name']");
    await waitUntil(
        () =>
            queryValue(".o_field_widget.o_field_advanced_record_picker input") ===
            "Acme",
        { timeout: 1000 }
    );
    await waitUntil(
        () => document.querySelector(".o_form_editable")?.classList.contains("o_form_dirty"),
        { timeout: 1000 }
    );

    expect(".o_field_widget.o_field_advanced_record_picker input").toHaveValue("Acme");
    expect(".o_form_editable").toHaveClass("o_form_dirty");
});

test("keeps the native many2one usable when the profile is missing", async () => {
    onRpc("advanced.record.picker.profile", "search_read", () => []);

    await mountView({
        type: "form",
        resModel: "picker.host",
        resId: 1,
        arch: `
            <form>
                <field name="partner_id" widget="advanced_record_picker"
                    options="{'picker_profile': 'missing_picker'}"/>
            </form>`,
    });

    expect(".o_field_widget.o_field_advanced_record_picker").toHaveCount(1);
    expect(".o_field_widget.o_field_advanced_record_picker input").toHaveCount(1);
    expect(".o_field_widget.o_field_advanced_record_picker button.oi-search").toHaveCount(0);
});

test("does not expose the advanced entry for a readonly field", async () => {
    await mountView({
        type: "form",
        resModel: "picker.host",
        resId: 1,
        arch: `
            <form>
                <field name="partner_id" widget="advanced_record_picker" readonly="1"
                    options="{'picker_profile': 'partner_picker'}"/>
            </form>`,
    });

    expect(".o_field_widget.o_field_advanced_record_picker").toHaveCount(1);
    expect(".o_field_widget.o_field_advanced_record_picker button.oi-search").toHaveCount(0);
});
