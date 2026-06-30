# -*- coding: utf-8 -*-
{
    'name': "World Depot",

    'summary': "Logistics and Supply Chain Management System",

    'description': """
 Logistics and Supply Chain Management System for World Depot
    """,

    'author': "World Depot B.V.",
    'website': "https://www.worlddepot.eu",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','contacts','web','mail','stock','project','product', 'stock_barcode'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        #'views/views.xml',
        #'views/templates.xml',
        #'vies/my_partner.xml',
        'views/location_type.xml',
        'views/my_project.xml',
        'views/my_stock.xml',
        'views/my_product.xml',
       # 'views/my_user.xml',
       # 'views/my_report.xml',
        'views/my_picking_type.xml',
        'views/inbound_order.xml',
        'views/outbound_order.xml',
        #'views/portal_inventory_reporting.xml',
        'views/api_logs.xml',

        'views/my_api_user.xml',
        'views/my_product_template.xml',
        'views/inbound_order_summary.xml',
        'views/outbound_order_summary.xml',
        'views/transfer_order_views.xml',
        'views/outbound_order_sn_detail.xml',
        'views/linglong_inbound_temp.xml',
        'views/product_duplicate.xml',
        'views/hoymiles/hoymiles_api_logs.xml',
        'views/hoymiles/hoymiles_api_urls.xml',
        'views/charge_item.xml',
        'views/charge_module.xml',
        'views/charge_module_wizard.xml',
        'views/charge_summary.xml',
        'views/inbound_order_charge.xml',
        'views/outbound_order_pack_info.xml',
        'views/outbound_order_charge.xml',
        'views/my_dashboard.xml',
        'views/my_route.xml',
        'views/my_stock_report_linglong_views.xml',
        'views/inbound_order_deepseek_checker.xml',
        'views/outbound_order_deepseek_checker.xml',
        #'views/my_excel_template.xml',
        #'views/pallet_barcode_assets.xml',
        #'views/sequence.xml',
        'views/my_sequence.xml',
        'views/menus.xml',
        #'views/report_wd_picking_templates.xml',
        #'views/report_wd_picking_action.xml',
        #'views/pallet_barcode_action.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Load our components after stock_barcode
            #'web/static/src/**/*',
            #'stock_barcode/static/src/**/*',
            #'worlddepot/static/src/js/pallet_barcode.js',
            #'worlddepot/static/src/xml/pallet_barcode_assets.xml',
            #'stock_barcode/static/src/components/main.js',
            #'web/static/src/core/barcode/barcode_dialog.js',
            #'worlddepot/static/src/js/pallet_scan.js',
            #'worlddepot/static/src/js/pallet_barcode_patch.js',
            'worlddepot/static/src/models/barcode_picking_model_patch.js',
            'worlddepot/static/src/components/grouped_line_patch.js',
            'worlddepot/static/src/scss/barcode_overdone.scss',
            'worlddepot/static/src/scss/worlddepot_required_field_highlight.scss',
        ],
    },
    'license': 'LGPL-3',
}

