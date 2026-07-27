# -*- coding: utf-8 -*-
{
    'name': "search_product_change",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': '进口/进口',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','product','stock','worlddepot'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/stock_security.xml',
        'views/views.xml',
        'views/modify_lot_name_views.xml',
        'views/project_action_views.xml',

    ],
    'license': 'LGPL-3',
}

