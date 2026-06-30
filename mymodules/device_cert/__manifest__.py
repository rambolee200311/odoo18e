{
    'name': 'Global Access Gateway（GAG）',
    'version': '18.0.1.0.0',
    'author': 'World Depot B.V.',
    'category': 'Security',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/device_views.xml',
        'views/device_log_views.xml',
        'data/email_template.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}