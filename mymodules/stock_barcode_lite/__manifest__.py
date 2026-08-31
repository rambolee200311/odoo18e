# -*- coding: utf-8 -*-
{
    "name": "Stock Barcode Lite",
    "summary": "Chenyang Chemical warehouse customizations",
    "description": """
Chenyang Chemical warehouse customizations.
    """,
    "author": "World Depot B.V.",
    "category": "Warehouse",
    "version": "18.0.1.2.0",
    "depends": ["worlddepot", "account", "stock_barcode", "product_expiry"],
    "data": [
        "security/ir.model.access.csv",
        'security/security.xml',
        "data/pda_internal_transfer_cron.xml",

        "reports/inbound_pallet_label_report.xml",
        "reports/outbound_lot_code_label_report.xml",
        "reports/inbound_lot_code_label_report.xml",

        "views/inbound_order_views.xml",
        "views/outbound_order_views.xml",
        "views/stock_picking_views.xml",
        "views/sunrise_stock_report_views.xml",
        "views/sunrise_inbound_pallet_summary_report_views.xml",
        "views/sunrise_location_occupancy_report_views.xml",
        "views/menu.xml",
        "views/sunrise_api_views.xml",
        "views/sunrise_product_master_import_views.xml",
        "views/sunrise_order_import_views.xml",
        "views/move_line_location_import_views.xml",
        "views/stock_quant_package_inherit_views.xml",
        'views/product_views.xml',
        "views/project_project_views.xml",
        "views/sunrise_product_batch_specification_import_views.xml",

        "wizard/inbound_product_import_wizard_views.xml",
        "wizard/outbound_product_import_wizard_views.xml",


    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_lite/static/src/js/main.js",
            "stock_barcode_lite/static/src/js/homepage.js",
            "stock_barcode_lite/static/src/js/inbound_flow.js",
            "stock_barcode_lite/static/src/js/whole_outbound.js",
            "stock_barcode_lite/static/src/js/disassembly_outbound.js",
            "stock_barcode_lite/static/src/js/internal_transfer.js",
            "stock_barcode_lite/static/src/js/barcode_kanban_patch.js",
            "stock_barcode_lite/static/src/xml/homepage.xml",
            "stock_barcode_lite/static/src/xml/internal_transfer.xml",
            "stock_barcode_lite/static/src/xml/inbound.xml",
            "stock_barcode_lite/static/src/xml/outbound_whole_pallet.xml",
            "stock_barcode_lite/static/src/xml/outbound_disassembly.xml",
            "stock_barcode_lite/static/src/scss/_common.scss",
            "stock_barcode_lite/static/src/scss/_pallet.scss",
            "stock_barcode_lite/static/src/scss/_homepage.scss",
            "stock_barcode_lite/static/src/scss/_inbound.scss",
            "stock_barcode_lite/static/src/scss/_outbound.scss",
        ],
    },
    "license": "LGPL-3",
    "application": True,
    "installable": True,
}
