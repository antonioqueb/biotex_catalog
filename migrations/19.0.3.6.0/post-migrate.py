"""Códigos de barras de relleno en presentaciones (``product.uom``).

Mientras ``barcode`` era obligatorio, los operadores capturaban "NA", "1" o similares para poder guardar.
Con el campo ya opcional (la actualización del módulo retira el NOT NULL antes de este script) esos valores
se vacían; cada uno queda registrado en el log con su producto para trazabilidad. Los códigos reales no se tocan.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

PLACEHOLDERS = ('NA', 'N/A', 'NA.', 'PENDIENTE', 'SIN CODIGO', 'SIN CÓDIGO', '1', '0', '-', '.')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rows = env['product.uom'].with_context(active_test=False).search([('barcode', '!=', False)])
    placeholders = rows.filtered(lambda r: (r.barcode or '').strip().upper() in PLACEHOLDERS)
    for row in placeholders:
        _logger.info('Presentación %s de "%s": se vacía el código de relleno %r.', row.id, row.product_id.display_name, row.barcode)
    if placeholders:
        cr.execute('UPDATE product_uom SET barcode = NULL WHERE id IN %s', (tuple(placeholders.ids),))
        _logger.info('%d presentación(es) con código de relleno limpiadas.', len(placeholders))
