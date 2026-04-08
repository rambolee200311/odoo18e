# -*- coding: utf-8 -*-
{
    'name': "bonded_mange",

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
    'depends': ['base','worlddepot'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/sequence_inbound_data.xml',
        'bonded_views/stock_picking_inherit_views.xml',
        'bonded_views/stock_move_inherit_views.xml',
        'bonded_views/stock_move_line_inherit_views.xml',
        'bonded_views/stock_quant_inherit_views.xml',
        'bonded_views/inbound_order_inherit_views.xml',
        'bonded_views/outbound_order_inherit_views.xml',
        'bonded_views/product_product_inherit_views.xml',
        'bonded_views/bonded_customs_mrn_audit_log_views.xml',
        'bonded_views/mrn_stock_query_views.xml',



        'report/mrn_regulatory_report_action.xml',
        'report/mrn_regulatory_report_templates.xml',
        'report/mrn_stock_query_report_action.xml',
        'report/mrn_stock_query_report_templates.xml',
        'bonded_views/mrn_regulatory_report_views.xml',
        'bonded_views/mrn_master_bridge.xml',
        'bonded_views/identifier_stock_ledger_views.xml',

        'wizard/change_t1_customs_status_wizard_views.xml',

    ],
    # only loaded in demonstration mode
    'application': True,
}

