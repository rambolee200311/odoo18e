# -*- coding: utf-8 -*-
{
    "name": "Stock Barcode Patch",
    "summary": "Adds duplicate serial number scanning check in barcode picking",
    "description": """
This module adds a check to prevent duplicate serial number scanning during the outbound barcode scanning process.
    """,
    "author": "Custom",
    "category": "Warehouse",
    "version": "18.0.1.0.0",
    "depends": ["stock_barcode"],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_patch/static/src/js/barcode_kanban_patch.js",
            "stock_barcode_patch/static/src/js/grouped_line_patch.js",
            # "stock_barcode_patch/static/src/js/sn_check_patch.js",
        ],
    },
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
