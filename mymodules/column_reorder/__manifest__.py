{
    # App information
    'name': 'Column Reorder & Filter',
    'version': '18.0.1.0.0',
    'summary': 'Column reorder and per-column inline filtering for list views.',
    'description': 'Column Reorder & Filter lets backend users drag to reorder columns and filter each column directly from the list view header. The selected order is remembered per view in the browser.',
    'category': 'Tools',
    'license': 'LGPL-3',

    # Author
    'author': 'Techno Stellar',
    'maintainer': 'Techno Stellar',

    # Dependencies
    'depends': ['web'],

    # Views & Data
    'assets': {
        'web.assets_backend': [
            'column_reorder/static/src/js/*.js',
            'column_reorder/static/src/xml/*.xml',
            'column_reorder/static/src/scss/*.scss',
        ],
    },

    # Technical
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}