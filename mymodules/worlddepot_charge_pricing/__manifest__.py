# -*- coding: utf-8 -*-
{
    'name': "计费主数据 + 计费引擎",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
报价、费用项目、规则、取数规则、向导、引擎逻辑
    """,

    'author': "roger",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': '',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','worlddepot'],

    # always loaded
    'data': [
        "security/ir.model.access.csv",
        "wizard/charge_quotation_add_wizard_views.xml",
        "views/charge_quotation_views.xml",
        "views/charge_rule_views.xml",
        "views/charge_quantity_rule_views.xml",
        "data/ir_sequence_quotation.xml",



    ],

}

