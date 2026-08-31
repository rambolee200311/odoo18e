# -*- coding: utf-8 -*-

{
    'name': 'Hide Default Portal Menus',
    'summary': 'Remove default portal navigation items from the sidebar',
    'description': '''
Hide Default Portal Menus
========================
Removes the standard portal menu items (Your Orders, Your Invoices, Projects, etc.)
from the portal sidebar to provide a cleaner portal experience.

Menu items removed:
- Your Orders (sale module)
- Your Invoices (account module)
- Projects (project module)
- Our Invoices (account module)
- Connection & Security (portal module)
- Documents (documents module)
    ''',
    'author': 'Custom',
    'category': 'Website',
    'version': '18.0.1.0.0',
    'depends': ['portal', 'website'],
    'data': [
        'views/portal_patch.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
}
