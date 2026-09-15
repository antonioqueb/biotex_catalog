"""Vacía los códigos de barras de relleno en presentaciones (``product.uom``).

Mientras ``barcode`` era obligatorio (antes de biotex_catalog 19.0.3.6.0) los operadores capturaban "NA", "1"
o similares para poder guardar. Este script NO se ejecuta solo en la actualización del módulo: el instalador
formal de producción rechaza cualquier migración que altere tablas de negocio, así que la limpieza se hace a mano,
con revisión, desde un shell de Odoo del entorno que corresponda:

    docker compose ... run -T --rm --no-deps odoo odoo shell -d bioteczac --no-http < tools/clean_placeholder_barcodes.py

Primero lista lo que encontró; solo escribe si se ejecuta con ``APPLY = True``.
"""
APPLY = False
PLACEHOLDERS = ('NA', 'N/A', 'NA.', 'PENDIENTE', 'SIN CODIGO', 'SIN CÓDIGO', '1', '0', '-', '.')

rows = env['product.uom'].with_context(active_test=False).search([('barcode', '!=', False)])  # noqa: F821 (shell de Odoo)
placeholders = rows.filtered(lambda r: (r.barcode or '').strip().upper() in PLACEHOLDERS)
for row in placeholders:
    print('presentación %s de "%s": código de relleno %r' % (row.id, row.product_id.display_name, row.barcode))
print('%d presentación(es) con código de relleno' % len(placeholders))
if APPLY and placeholders:
    env.cr.execute('UPDATE product_uom SET barcode = NULL WHERE id IN %s', (tuple(placeholders.ids),))  # noqa: F821
    env.cr.commit()  # noqa: F821
    print('limpiadas')
