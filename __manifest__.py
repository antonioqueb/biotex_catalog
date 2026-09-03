{
    'name': 'Catálogo de insumos',
    'summary': 'Grupo > familia > clave, descripción estructurada, marcas, fotos, estado de clasificación, asistente guiado, sinónimos, etiqueta QR',
    'version': '19.0.1.0.0',
    'category': 'Distribución de insumos',
    'author': 'Alphaqueb Consulting SAS',
    'license': 'LGPL-3',
    'icon': '/biotex_catalog/static/description/icon.svg',
    'depends': ['biotex_base', 'product', 'stock', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'security/catalog_security.xml',
        'data/catalog_data.xml',
        'views/biotex_brand_views.xml',
        'views/biotex_equipment_views.xml',
        'views/product_category_views.xml',
        'views/product_template_views.xml',
        'views/classifier_action.xml',
        'wizard/reorder_wizard_views.xml',
        'report/product_label_report.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'biotex_catalog/static/src/**/*',
        ],
    },
    'installable': True,
}
