# -*- coding: utf-8 -*-
{
    "name": "WD Account Extension",
    "version": "1.0.0",
    "category": "Accounting",
    "summary": "Common accounting enhancements",
    "depends": ["account", "worlddepot"],
    "pre_init_hook": "migrate_account_extension_xml_ids",
    "data": [
        "data/account_account_data.xml",
        "views/account_account_inherit_views.xml",
        "views/account_move_inherit_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
