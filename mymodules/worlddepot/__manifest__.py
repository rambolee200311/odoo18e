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
    'depends': ['base','web','mail','stock','project'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/my_project.xml',
        'views/my_stock.xml',
        'views/views.xml',
        'views/templates.xml',
        'views/inbound_order.xml',
        'views/outbound_order.xml',
        'views/sequence.xml',
        'views/menus.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}

