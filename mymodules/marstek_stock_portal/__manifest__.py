# -*- coding: utf-8 -*-
{
    'name': "Marstek Stock Portal",

    'summary': "Marstek Customer Stock Query Portal",

    'description': """
Marstek Stock Portal
====================
Customer-facing portal for stock query and inventory management.
This module provides read-only access to warehouse inventory data.

Features:
- Stock Overview (view all inventory by pallet/container/BL)
- Container Query (query inventory by container number)
- Inbound Query (view inbound orders)
- Outbound Query (view outbound orders)
- SN Query (query serial numbers for outbound items)
    """,

    'author': "Marstek",

    'website': "https://www.marstek.com",

    'category': 'Website',

    'version': '1.0.0',

    'depends': [
        'base',
        'web',
        'portal',
        'website',
    ],

    'data': [
        'security/ir.model.access.csv',
        'portal/marstek_portal_templates.xml',
        'portal/marstek_owl_templates.xml',
    ],

    # 'assets': {
    #     'web.assets_backend': [
    #         'marstek_stock_portal/static/src/main.js',
    #         'marstek_stock_portal/static/src/css/portal.css',
    #     ],
    # },

    'license': 'LGPL-3',
}
