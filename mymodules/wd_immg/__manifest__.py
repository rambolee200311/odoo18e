# -*- coding: utf-8 -*-
{
    'name': "进口货代管理模块",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "roger",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': '进口/进口',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','account','worlddepot'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_operation.xml',
        'data/ir_sequence_quotation.xml',
        'wizard/charge_quotation_add_wizard_views.xml',
        'views/charge_priceing_views/charge_quotation_views.xml',
        'views/handover_views/operation_order_handover_views.xml',
        'views/waybill_inherit_views.xml',

        'views/settlement_account_views/account_move_inherit_views.xml',
        'views/all_menu.xml',

    ],
    'application': True,

}

