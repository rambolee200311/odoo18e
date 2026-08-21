# -*- coding: utf-8 -*-

{
    "name": "Marstek Stock Portal",
    "summary": "Read-only stock portal backend methods for Marstek customers",
    "description": """
Read-only ORM methods for Marstek portal stock, inbound, outbound, SN, and attachment queries.
    """,
    "author": "World Depot B.V.",
    "category": "进口/进口",
    "version": "18.0.1.0.0",
    "depends": ["worlddepot", "portal", "website", "stock","stock_barcode_lite"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/res_user_views.xml",
        "views/project_project_views.xml",
        "report/marstek_portal_export_report.xml",
        "report/report_stock_templates.xml",
        "portal/marstek_portal_menus.xml",
        "portal/portal_stock.xml",
        "portal/portal_stock_history.xml",
        "portal/portal_container.xml",
        "portal/portal_inbound.xml",
        "portal/portal_outbound.xml",
        "portal/portal_sn_query.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "assets": {
        "web.assets_frontend": [
            "marstek_stock_portal/static/src/js/marstek_table_utils.js",
            "marstek_stock_portal/static/src/js/marstek_inbound_card.js",
            "marstek_stock_portal/static/src/js/marstek_outbound_card.js",
            "marstek_stock_portal/static/src/js/marstek_stock_card.js",
            "marstek_stock_portal/static/src/js/stock_movement_history.js",
            "marstek_stock_portal/static/src/css/marstek_collapsible.css",
            "marstek_stock_portal/static/src/css/portal.css",
        ],
    },
}
