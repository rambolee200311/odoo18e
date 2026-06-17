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
        "views/stock_picking_views.xml",
        "views/sunrise_api_views.xml",
        "views/menu.xml",
        "views/stock_quant_package_inherit_views.xml",

        "wizard/inbound_product_import_wizard_views.xml",
        "wizard/outbound_product_import_wizard_views.xml",


    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_lite/static/src/js/main.js",
            "stock_barcode_lite/static/src/js/homepage.js",
            "stock_barcode_lite/static/src/js/inbound_flow.js",
            "stock_barcode_lite/static/src/js/outbound_flow.js",
            "stock_barcode_lite/static/src/js/whole_outbound.js",
            "stock_barcode_lite/static/src/js/disassembly_outbound.js",
            "stock_barcode_lite/static/src/xml/homepage.xml",
            "stock_barcode_lite/static/src/xml/inbound.xml",
            "stock_barcode_lite/static/src/xml/outbound.xml",
            "stock_barcode_lite/static/src/xml/outbound_whole_pallet.xml",
            "stock_barcode_lite/static/src/xml/outbound_disassembly.xml",
            "stock_barcode_lite/static/src/css/_common.scss",
            "stock_barcode_lite/static/src/css/_homepage.scss",
            "stock_barcode_lite/static/src/css/_inbound.scss",
        ],
    },
    "license": "LGPL-3",
    "application": True,
    "installable": True,
}
