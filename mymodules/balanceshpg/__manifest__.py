# -*- coding: utf-8 -*-
{
    'name': "Balance SHPG",

    'summary': "Export Business Management System",

    'description': """
 Logistics and Supply Chain Management System for World Depot
    """,

    'author': "Balance SHPG B.V.",
    'website': "https://www.balanceshpg.eu",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','contacts','web','mail','stock','project','product',],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [

        ],
    },
    'license': 'LGPL-3',
}

