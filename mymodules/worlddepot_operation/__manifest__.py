# -*- coding: utf-8 -*-
{
    'name': "作业体系",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
作业统一主表 + 各作业扩展表 + 文件清单
    """,

    'author': "roger",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['account','worlddepot_charge_pricing'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_operation.xml',
        'views/operation_order_handover_views.xml',
        'views/account_move_inherit_views.xml',
        'views/all_menu.xml',
    ],

}

