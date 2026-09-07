from markupsafe import Markup, escape
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    biotex_import_sha256 = fields.Char(string='Huella del archivo de origen', readonly=True, copy=False, index=True)
    biotex_import_source = fields.Json(string='Renglones originales y remapeo', readonly=True, copy=False, groups='base.group_user')
    biotex_import_detail = fields.Html(string='Datos del archivo de origen', compute='_compute_import_detail',
                                      groups='base.group_user', sanitize=True)
    biotex_import_review = fields.Text(string='Pendientes de validación de la migración', readonly=True, copy=False)
    biotex_import_status = fields.Selection([
        ('reference', 'Importado: precios de referencia'), ('review', 'Revisar identidad o presentación'),
        ('validated', 'Revisado por Dirección'),
    ], string='Validación de origen', readonly=True, copy=False)
    biotex_import_validated_by = fields.Many2one('res.users', readonly=True, copy=False)
    biotex_import_validated_on = fields.Datetime(readonly=True, copy=False)

    @api.depends('biotex_import_source')
    def _compute_import_detail(self):
        for product in self:
            source = product.biotex_import_source or {}
            sections = []
            columns = source.get('columns', [])
            for row in source.get('rows', []):
                values = row.get('values', [])
                formulas = row.get('formulas', [])
                cells = []
                for index, label in enumerate(columns):
                    value = values[index] if index < len(values) else None
                    formula = formulas[index] if index < len(formulas) else None
                    formula = formula if isinstance(formula, str) and formula.startswith('=') else ''
                    cells.append(Markup('<tr><td>%s</td><th scope="row">%s</th><td>%s</td><td>%s</td></tr>') % (
                        index + 1, escape(label or 'Sin encabezado'),
                        escape(str(value) if value is not None else '—'), escape(formula)))
                sections.append(Markup('<h4>Hoja %s · Fila %s</h4>'
                    '<div class="table-responsive"><table class="table table-sm table-striped">'
                    '<thead><tr><th>Columna</th><th>Campo del Excel</th><th>Valor de origen</th>'
                    '<th>Fórmula de origen</th></tr></thead><tbody>%s</tbody></table></div>') % (
                        escape(str(row.get('worksheet') or source.get('worksheet') or '20_REMAPEO')),
                        escape(str(row.get('worksheet_row', ''))), Markup('').join(cells)))
            attachment = source.get('source_attachment_id')
            if isinstance(attachment, int) and attachment > 0:
                sections.insert(0, Markup('<p><a href="/web/content/%s?download=1">Descargar Excel original con todas sus hojas</a></p>') % attachment)
            product.biotex_import_detail = Markup('').join(sections)

    def write(self, values):
        protected = {'biotex_import_sha256', 'biotex_import_source', 'biotex_import_review',
                     'biotex_import_status', 'biotex_import_validated_by', 'biotex_import_validated_on'}
        if not self.env.su and protected.intersection(values):
            raise AccessError('El origen de la migración es inmutable. Use la validación de Dirección.')
        if not self.env.su and (values.get('sale_ok') or values.get('purchase_ok')):
            if any(p.biotex_import_sha256 and p.biotex_import_status != 'validated' for p in self):
                raise UserError('Valide primero las incidencias, identidad y presentación de origen.')
        return super().write(values)

    def action_validate_import(self):
        if not self.env.user.has_group('biotex_base.group_biotex_direction'):
            raise UserError('Dirección debe validar las incidencias y la presentación de origen.')
        for product in self:
            if not product.biotex_import_sha256:
                continue
            if not product.biotex_content or not product.biotex_classifier_id or not product.biotex_brand_id:
                raise UserError('Complete la unidad indivisible y la clasificación antes de validar.')
            product.sudo().write({'biotex_import_status': 'validated',
                           'biotex_import_validated_by': self.env.user.id,
                           'biotex_import_validated_on': fields.Datetime.now(),
                           'sale_ok': True, 'purchase_ok': True})
        return True
