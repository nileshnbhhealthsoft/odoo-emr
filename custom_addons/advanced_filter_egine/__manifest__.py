{
    'name': 'Advanced Filter Engine',
    'version': '18.0.1.0.0',
    'summary': 'Dynamic Advanced Filtering Engine for all Odoo models',
    'author': 'Your Name',
    'category': 'Tools',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/advanced_filter_views.xml',
        'views/demo_edi_views.xml',
        'views/data_filter_wizard_views.xml',
        'data/cleanup_native_favorites.xml',
    ],
    'demo': [
        'data/demo_edi_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_filter_engine/static/src/js/advanced_filter_widget.js',
            'advanced_filter_engine/static/src/xml/advanced_filter_template.xml',
            'advanced_filter_engine/static/src/scss/advanced_filter.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
