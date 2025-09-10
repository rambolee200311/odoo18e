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
        # 'security/ir.model.access.csv',
        #'views/views.xml',
        #'views/templates.xml',
        #'vies/my_partner.xml',
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
        'views/waybill.xml',
        'views/my_api_user.xml',
        'views/my_product_template.xml',
        'views/inbound_order_summary.xml',
        'views/outbound_order_summary.xml',
        'views/outbound_order_sn_detail.xml',
        'views/linglong_inbound_temp.xml',
        #'views/my_excel_template.xml',
        #'views/pallet_barcode_assets.xml',
        #'views/sequence.xml',
        'views/my_sequence.xml',
        'views/menus.xml',
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
        ],
    },
    'license': 'LGPL-3',
}

