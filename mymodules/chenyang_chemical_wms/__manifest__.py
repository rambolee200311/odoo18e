# -*- coding: utf-8 -*-
{
    "name": "Chenyang Chemical WMS",
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
        "views/inbound_product_import_wizard_views.xml",
        "views/inbound_order_views.xml",
    ],
    "license": "LGPL-3",
    "application": True,
    "installable": True,
}
