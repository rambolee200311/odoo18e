# -*- coding: utf-8 -*-

{
    "name": "Stock Operation Portal",
    "summary": "Stock operation portal for PDA/PC - Inbound, Outbound and Transfer orders",
    "description": """
Stock Operation Portal
=====================
Enable users to create and manage stock operations via PDA or PC:
- Inbound Orders (入库订单)
- Outbound Orders (出库订单)
- Transfer/Internal Operations (仓内操作/调拨订单)
    """,
    "author": "World Depot B.V.",
    "category": "Warehouse",
    "version": "18.0.1.0.0",
    "depends": ["worlddepot", "portal", "website", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "portal/portal_menus.xml",
        "portal/portal_container.xml",
        "portal/portal_inbound.xml",
        "portal/portal_outbound.xml",
        "portal/portal_transfer.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "assets": {
        "web.assets_frontend": [
            "stock_operation_portal/static/src/js/operation_form.js",
            "stock_operation_portal/static/src/js/product_lookup.js",
            "stock_operation_portal/static/src/css/operation_portal.css",
        ],
    },
}
