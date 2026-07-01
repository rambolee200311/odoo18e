# -*- coding: utf-8 -*-
{
    'name': 'Dynamic One2many Preview Widget',
    'version': '18.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Display One2many records dynamically inside parent list views',
    'description': """
Dynamic One2many Preview Widget for Odoo 18
===========================================
This module provides a reusable backend widget to display One2many records
inside parent list views using configurable XML options.
    """,
    'author': 'Mind Spark Technologies',
    'website': 'https://www.mindsparktechnologies.com',
    'depends': ['web','sale_management'],
    'data': [
        'views/example_usage.xml',
        'views/sale_order_view.xml'
    ],
    'assets': {
        'web.assets_backend': [
            'mst_dynamic_o2m_preview/static/src/js/dynamic_one2many_preview.js',
            'mst_dynamic_o2m_preview/static/src/xml/dynamic_one2many_preview.xml',
            'mst_dynamic_o2m_preview/static/src/css/dynamic_one2many_preview.css',
        ],
    },
    "images": [
        "static/description/banner.png",
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
