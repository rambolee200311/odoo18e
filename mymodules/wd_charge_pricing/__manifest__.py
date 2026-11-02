# -*- coding: utf-8 -*-
{
    "name": "WD Charge Pricing",
    "summary": "Shared charge items and logistics quotations",
    "version": "18.0.1.0.0",
    "category": "Operations",
    "depends": ["base", "mail", "project"],
    "pre_init_hook": "migrate_charge_pricing_xml_ids",
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_quotation.xml",
        "views/charge_item_views.xml",
        "wizard/charge_quotation_add_wizard_views.xml",
        "views/charge_quotation_views.xml",
        "views/vendor_cost_quotation_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "wd_charge_pricing/static/src/scss/charge_pricing_required_highlight.scss",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
