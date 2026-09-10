"""Unidad de las medidas desde el catálogo de unidades de medida: crea las típicas que falten y enlaza los textos ya capturados."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    created = env['biotex.measure.type']._ensure_units()
    pending = env['biotex.product.measure'].search([('unit_uom_id', '=', False)])
    matched = 0
    for text in set(pending.mapped('unit')):
        uom = env['uom.uom'].search([('name', '=ilike', text)], limit=1)
        if uom:
            rows = pending.filtered(lambda r: r.unit == text)
            rows.write({'unit_uom_id': uom.id})
            matched += len(rows)
    _logger.info('Unidades creadas: %s. Medidas enlazadas a uom.uom: %d de %d.', created.mapped('name'), matched, len(pending))
