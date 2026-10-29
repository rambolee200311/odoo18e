# -*- coding: utf-8 -*-
{
    'name': 'WD Product Profile',
    'summary': 'Shared product trade, logistics and dangerous goods profile',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'depends': ['product','stock_delivery'],
    'data': [
        'views/product_template_views.xml',
        'views/product_product_views.xml',
    ],
    'installable': True,
    "application": True,
    'license': 'LGPL-3',
}
