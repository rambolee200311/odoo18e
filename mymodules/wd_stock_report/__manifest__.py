# -*- coding: utf-8 -*-
{
    "name": "WD Stock Report",
    "summary": "Shared warehouse stock reports",
    "version": "18.0.1.1.0",
    "category": "Warehouse",
    "depends": ["blind_stock_count"],
    "pre_init_hook": "migrate_stock_report_xml_ids",
    "data": [
        "security/ir.model.access.csv",
        "views/stock_pallet_detail_report_views.xml",
        "views/sunrise_stock_report_views.xml",
        "views/sunrise_inbound_pallet_summary_report_views.xml",
        "views/sunrise_outbound_pallet_summary_report_views.xml",
        "views/sunrise_location_occupancy_report_views.xml",
        "views/sunrise_monthly_category_pallet_report_views.xml",
        "views/sunrise_report_menu.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
