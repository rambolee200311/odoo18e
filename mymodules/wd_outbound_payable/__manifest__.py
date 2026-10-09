# -*- coding: utf-8 -*-
{
    "name": "Outbound Payable",
    "version": "1.0.0",
    "category": "Warehouse",
    "summary": "Outbound order payable records",
    "depends": ["account", "wd_account_extension", "wd_iffm", "worlddepot"],
    "data": [
        "security/ir.model.access.csv",
        "views/outbound_order_payable.xml",
        "views/account_move.xml",
        "views/statement_period.xml",
    ],
    "installable": True,
    'application': True,
    "license": "LGPL-3",
}
