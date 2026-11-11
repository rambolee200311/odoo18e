/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useState } from "@odoo/owl";

export class BondedPalletGroupedListRenderer extends ListRenderer {
    static rowsTemplate = "wd_bonded_wms.BondedPalletGroupedListRenderer.Rows";

    setup() {
        super.setup();
        this.pallet_group_state = useState({ folded: {} });
    }

    get pallet_groups() {
        const groups = new Map();
        for (const record of this.props.list.records) {
            const pallet_no = record.data.pallet_no || false;
            const key = pallet_no || "__no_pallet_number__";
            if (!groups.has(key)) {
                groups.set(key, { key, label: pallet_no || _t("No Pallet Number"), records: [] });
            }
            groups.get(key).records.push(record);
        }
        return [...groups.values()];
    }

    is_pallet_group_folded(key) {
        return this.pallet_group_state.folded[key] !== false;
    }

    toggle_pallet_group(key) {
        this.pallet_group_state.folded[key] = !this.is_pallet_group_folded(key);
    }
}

export class BondedPalletGroupedX2ManyField extends X2ManyField {
    static components = { ...X2ManyField.components, ListRenderer: BondedPalletGroupedListRenderer };
}

registry.category("fields").add("bonded_pallet_grouped_one2many", { ...x2ManyField, component: BondedPalletGroupedX2ManyField });
