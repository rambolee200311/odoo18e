# -*- coding: utf-8 -*-
{
    "name": "Outbound Payable",
    "version": "1.0.0",
    "category": "Operations",
    "summary": "Outbound order payable records",
    "depends": ["account", "wd_account_extension", "worlddepot"],
    "data": [
        "security/ir.model.access.csv",
        "views/outbound_order_payable.xml",
        "views/account_move.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
