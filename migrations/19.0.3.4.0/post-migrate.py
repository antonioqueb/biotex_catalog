"""Completa códigos y descripciones de los tipos de empaque ya existentes y enlaza las medidas capturadas
como texto libre con el catálogo de atributos dimensionales."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

PACKAGE_INFO = {
    'package_type_pieza': ('PZA', 'Unidad suelta sin envase de agrupación.'),
    'package_type_sobre': ('SOB', 'Sobre sellado individual o múltiple.'),
    'package_type_bolsa': ('BOL', 'Bolsa de polietileno o similar.'),
    'package_type_caja': ('CAJ', 'Caja de cartón.'),
    'package_type_frasco': ('FRA', 'Frasco o botella.'),
    'package_type_tubo': ('TUB', 'Tubo colapsible.'),
    'package_type_paquete': ('PAQ', 'Paquete o bulto.'),
    'package_type_juego': ('JGO', 'Juego o set de piezas.'),
    'package_type_unidad': ('UND', 'Equipo o mobiliario que se entrega armado.'),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, (code, description) in PACKAGE_INFO.items():
        record = env.ref('biotex_catalog.%s' % xmlid, raise_if_not_found=False)
        if record:
            record.write({k: v for k, v in (('code', code), ('description', description)) if not record[k]})
    Type = env['biotex.measure.type']
    pending = env['biotex.product.measure'].search([('measure_type_id', '=', False)])
    matched = 0
    for text in set(pending.mapped('measure_type')):
        found = Type._find_by_text(text)
        if found:
            rows = pending.filtered(lambda r: r.measure_type == text)
            rows.write({'measure_type_id': found.id})
            matched += len(rows)
    _logger.info('Medidas enlazadas al catálogo de atributos: %d de %d; las demás conservan su texto.', matched, len(pending))
