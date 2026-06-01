# -*- coding: utf-8 -*-
{
    "name": "Stock Barcode Lite",
    "summary": "Chenyang Chemical warehouse customizations",
    "description": """
Chenyang Chemical warehouse customizations.
    """,
    "author": "World Depot B.V.",
    "category": "Warehouse",
    "version": "18.0.1.0.0",
    "depends": ["worlddepot"],
    "data": [
        "security/ir.model.access.csv",

        "reports/inbound_pallet_label_report.xml",

        "views/inbound_order_views.xml",
        "views/outbound_order_views.xml",
        "views/menu.xml",

        "wizard/inbound_product_import_wizard_views.xml",
        "wizard/outbound_product_import_wizard_views.xml",

    ],
    "license": "LGPL-3",
    "application": True,
    "installable": True,
}
