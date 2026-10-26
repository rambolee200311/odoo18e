# -*- coding: utf-8 -*-
{
    "name": "Blind Stock Count",
    "summary": "Blind stock count scanning and pallet labels",
    "version": "18.0.1.0.0",
    "category": "Warehouse",
    "author": "World Depot B.V.",
    "depends": ["mail", "stock_barcode_lite", "queue_job"],
    "data": [
        "security/blind_stock_count_groups.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/queue_job_data.xml",
        "data/ir_cron_data.xml",
        "views/blind_stock_count_views.xml",
        "views/blind_stock_count_process_views.xml",
        "report/blind_stock_count_pallet_label.xml",
        "wizard/print_pallet_labels_views.xml",
        "wizard/generate_clearance_batch_views.xml",
        "views/stock_quant_package_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "blind_stock_count/static/src/js/blind_stock_count.js",
            "blind_stock_count/static/src/xml/blind_stock_count.xml",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    'application': True,
}
