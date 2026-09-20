# -*- coding: utf-8 -*-
{
    'name': 'Warehouse Value Add',

    'summary': 'Register warehouse value-added operations such as labeling and wrapping through Web and PDA.',

    'description': """
Warehouse Value Add
===================

This module records warehouse value-added operations such as labeling, wrapping, repacking, palletizing, and inventory counting.

Business Rules
--------------

1. Each work order has one operator. Different operators create their own work orders.

2. Multiple value-added work orders can be linked to the same inbound, outbound, or other warehouse order.

3. A work order can have one or more operation lines.

4. Operation lines use a unified Quantity / Time field. The unit is automatically derived from the selected operation type.

5. Related document numbers can be entered manually or scanned. The system resolves and links the corresponding warehouse document.

6. Images and videos can be uploaded as optional work evidence, with multiple attachments supported.

7. Desktop Web is used for office entry and history lookup.

8. The PDA is used for fast on-site entry. The current user is the read-only default operator and records their completed work.

9. Draft work orders can be saved and edited; operation lines can be added later, but submission requires at least one valid line.

10. Core business fields are locked after submission and cannot be edited directly.

11. System fields including work order number, creation time, submitter, and submission time are maintained automatically.

12. This module records operational facts only; it does not include value-added service billing, settlement, or financial accounting.
    """,

    'author': 'WD Dev',
    'website': '',
    'category': 'Warehouse',
    'version': '1.0.0',

    'depends': [
        'base',
        'mail',
        'web',
        'worlddepot',
    ],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/vas_operation_type_views.xml',
        'views/vas_order_views.xml',
        'views/vas_frontend_actions.xml',
        'views/vas_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'wd_warehouse_value_add/static/src/js/vas_dashboard.js',
            'wd_warehouse_value_add/static/src/js/vas_pda_action.js',
            'wd_warehouse_value_add/static/src/xml/vas_dashboard.xml',
            'wd_warehouse_value_add/static/src/xml/vas_pda_action.xml',
            'wd_warehouse_value_add/static/src/scss/vas_pda_action.scss',
        ],
        'web.assets_tests': [
            'wd_warehouse_value_add/static/tests/vas_pda_action_tests.js',
        ],
    },

    'installable': True,
    'auto_install': False,
    'application': True,

    'license': 'LGPL-3',
}
