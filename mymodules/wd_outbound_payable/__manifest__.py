# -*- coding: utf-8 -*-
{
    "name": "Outbound Payable",
    "version": "1.0.1",
    "category": "Warehouse",
    "summary": "Outbound order payable records",
    "depends": ["account", "wd_account_extension", "wd_charge_pricing", "wd_iffm", "worlddepot", "stock_barcode_lite", "wd_warehouse_value_add"],
    "data": [
        "security/ir.model.access.csv",
        "views/outbound_order_payable.xml",
        "views/inbound_order_payable.xml",
        "views/account_move.xml",
        "views/statement_period.xml",
    ],
    "installable": True,
    'application': True,
    "license": "LGPL-3",
}
