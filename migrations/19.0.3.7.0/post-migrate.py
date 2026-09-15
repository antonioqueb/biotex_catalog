"""Relleno histórico de "Clasificado por" (``biotex_classified_by_id`` / ``biotex_classified_on``).

Para cada producto con líneas de sesión aplicadas se toma la última aplicación (``applied_on`` y ``applied_by_id``
de ``biotex.classification.session.line``). Los productos clasificados solo con "Asignar clave" antes de esta
versión no tienen registro de autor y quedan vacíos. Solo se escriben las dos columnas nuevas.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE product_template p
           SET biotex_classified_by_id = last.applied_by_id, biotex_classified_on = last.applied_on
          FROM (SELECT DISTINCT ON (product_id) product_id, applied_by_id, applied_on
                  FROM biotex_classification_session_line
                 WHERE state = 'applied' AND applied_by_id IS NOT NULL
                 ORDER BY product_id, applied_on DESC NULLS LAST, id DESC) last
         WHERE p.id = last.product_id AND p.biotex_classified_by_id IS NULL
    """)
    _logger.info('"Clasificado por" rellenado desde sesiones aplicadas en %d producto(s).', cr.rowcount)
