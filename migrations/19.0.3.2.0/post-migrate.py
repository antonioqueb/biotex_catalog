"""Reordenamiento del folio a GG-FFF-CCC-MMMM-NN.

Solo se tocan las sesiones de clasificación **en borrador**: todavía no han escrito ninguna clave, así
que su prefijo se recalcula con el orden nuevo y sus consecutivos se vuelven a reservar bajo ese prefijo.
Las claves ya escritas en productos (orden anterior) y las sesiones confirmadas se conservan tal cual;
la decisión de migrarlas o no corresponde al negocio (ver docs/reordenamiento-folio.md).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Session = env['biotex.classification.session']
    drafts = Session.search([('state', '=', 'draft')])
    if not drafts:
        return
    drafts._compute_class_code()
    drafts.flush_recordset(['class_code', 'complete'])
    for session in drafts.filtered('class_code'):
        session._reassign_consecutives()
        _logger.info('Sesión de clasificación %s renumerada con el prefijo %s (%d líneas).', session.id, session.class_code, len(session.line_ids))
