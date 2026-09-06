from odoo import fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    biotex_import_sha256 = fields.Char(string='Huella del archivo de origen', readonly=True, copy=False, index=True)
    biotex_import_source = fields.Json(string='Renglones originales y remapeo', readonly=True, copy=False, groups='base.group_user')
    biotex_import_review = fields.Text(string='Pendientes de validación de la migración', readonly=True, copy=False)
    biotex_import_status = fields.Selection([
        ('reference', 'Importado: precios de referencia'), ('review', 'Revisar identidad o presentación'),
        ('validated', 'Revisado por Dirección'),
    ], string='Validación de origen', readonly=True, copy=False)
    biotex_import_validated_by = fields.Many2one('res.users', readonly=True, copy=False)
    biotex_import_validated_on = fields.Datetime(readonly=True, copy=False)

    def action_validate_import(self):
        if not self.env.user.has_group('biotex_base.group_biotex_direction'):
            raise UserError('Dirección debe validar las incidencias y la presentación de origen.')
        for product in self:
            if not product.biotex_import_sha256:
                continue
            product.write({'biotex_import_status': 'validated',
                           'biotex_import_validated_by': self.env.user.id,
                           'biotex_import_validated_on': fields.Datetime.now(),
                           'sale_ok': True, 'purchase_ok': True})
        return True
