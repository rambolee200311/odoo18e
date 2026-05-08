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
    'version': '0.2',

    # any module necessary for this one to work correctly
    'depends': ['base','account','worlddepot'],

    # hooks
    'post_init_hook': '_init_workbench_lanes',

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/all_menu.xml',
        'report/statement_period_report.xml',
        'report/statement_period_templates.xml',
        'data/sequence_operation.xml',
        'data/ir_sequence_quotation.xml',
        'data/account_account_data.xml',
        'data/workbench_test_data.xml',
        'data/operation_blocking_reason_data.xml',
        'data/portbase_api_data.xml',
        #'data/workbench_lane_data.xml',

        'wizard/charge_quotation_add_wizard_views.xml',
        'wizard/waybill_arrival_wizard_views.xml',
        'wizard/waybill_create_clearance_wizard_views.xml',
        'wizard/clearance/clearance_reclearance_wizard_views.xml',
        'wizard/protbase_import/portbase_waybill_import_wizard.xml',


        'views/charge_pricing_views/charge_quotation_views.xml',
        'views/charge_pricing_views/project_project_inherit_views.xml',
        'views/charge_pricing_views/waybill.xml',
        'views/charge_pricing_views/res_partner_inherit_views.xml',
        'views/charge_pricing_views/port_node_views.xml',
        'views/charge_pricing_views/portbase_webhook_log_views.xml',

        'views/handover_views/operation_order_handover_views.xml',
        'views/handover_views/handover_invoice_line_views.xml',
        'views/handover_views/handover_statement_period_views.xml',

        'views/clearance_views/operation_order_clearance_views.xml',
        'views/clearance_views/clearance_invoice_line_views.xml',
        'views/clearance_views/clearance_statement_period_views.xml',

        'views/settlement_account_views/statement_period_views.xml',



        'views/settlement_account_views/account_move_inherit_views.xml',
        'views/settlement_account_views/account_account_inherit_views.xml',

        'views/charge_item_inherit_views.xml',
        'views/workbench_views/operation_workbench_dashboard_data_views.xml',
        'views/workbench_views/operation_blocking_reason_views.xml',
        'views/workbench_views/operation_workbench_alert_rule_views.xml',



        'views/transportation_views/import_pickup_requirement_views.xml',
        'views/kanban_views/import_kanban_views.xml',
        'views/kanban_views/operation_workbench_card_kanban.xml',
        'views/kanban_views/workbench_lane_views.xml',
        'views/kanban_views/import_actions.xml',
        'views/dashboard_views.xml',
        'views/kanban_views/import_menu.xml',


    ],

    'application': True,

    'assets': {
        'web.assets_backend': [
            'wd_iffm/static/src/css/workbench_kanban.css',
            'wd_iffm/static/src/css/import_kanban_lane.css',
            'wd_iffm/static/src/css/home_page.css',
            'wd_iffm/static/src/scss/wd_required_field_highlight.scss',
            'wd_iffm/static/src/xml/workbench_home_page.xml',
            'wd_iffm/static/src/js/workbench_kanban_record.js',
            'wd_iffm/static/src/js/workbench_kanban_registry.js',
            'wd_iffm/static/src/js/workbench_home_action.js',
            'wd_iffm/static/src/js/workbench_action_registry.js',
        ],
    },
    'license': 'LGPL-3',

}

