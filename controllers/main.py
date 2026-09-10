"""Apertura del asistente de clasificación en una pestaña nueva.

La acción "Clasificar con asistente" de la lista de productos devuelve una URL a esta ruta. El
identificador de la sesión de clasificación viaja en la ruta, se guarda en la sesión HTTP del usuario
y se redirige a la acción cliente del asistente, que lo consume en su primer `workspace_bootstrap`.
Así la pestaña de productos no se toca y no dependemos de parámetros de URL en la acción cliente.
"""
from odoo import http
from odoo.http import request

from ..models.biotex_classification import HTTP_SESSION_KEY


class ClassificationOpen(http.Controller):

    @http.route('/biotex_catalog/classification/open/<int:session_id>', type='http', auth='user', website=False)
    def open_session(self, session_id, notice='', **kwargs):
        session = request.env['biotex.classification.session'].browse(session_id).exists()
        if session:
            session.check_access('read')
        request.session[HTTP_SESSION_KEY] = {'session_id': session.id if session else False, 'notice': (notice or '')[:1000]}
        action = request.env.ref('biotex_catalog.action_biotex_classifier')
        return request.redirect('/odoo/action-%d' % action.id)
