"""Familia = categoría de producto (árbol plano bajo la raíz). El grupo no es categoría: es una etiqueta."""
import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ProductCategory(models.Model):
    _inherit = 'product.category'

    biotex_group_id = fields.Many2one('biotex.group', string='Grupo', index=True, ondelete='restrict')
    biotex_division_id = fields.Many2one(related='biotex_group_id.division_id', string='División', store=True)
    biotex_code = fields.Char(string='Código de familia', size=3, help='3 letras, único dentro del grupo. Ej. EDO, GAS, SID.')
    biotex_composite = fields.Char(string='Clave compuesta', compute='_compute_composite', store=True)
    biotex_level = fields.Selection([('family', 'Familia'), ('other', 'Otra')], compute='_compute_level', store=True)
    biotex_status = fields.Selection([('active', 'Activa'), ('pending', 'Pendiente'), ('proposed', 'Propuesta')], default='active', string='Estatus')
    biotex_origin = fields.Char(string='Origen / nota del esquema')
    biotex_classifier_ids = fields.Many2many(
        'biotex.classifier', 'biotex_family_classifier_rel', 'family_id', 'classifier_id', string='Clasificadores autorizados',
        domain="[('group_id', '=', biotex_group_id)]")
    biotex_photo_required = fields.Boolean(string='Foto obligatoria', default=True)
    biotex_description_hint = fields.Char(string='Estructura de descripción', help='Ej. "Electrodo + tipo + forma + medida + presentación". Se muestra en el asistente.')
    biotex_default_tax_ids = fields.Many2many(
        'account.tax', 'biotex_categ_tax_rel', 'categ_id', 'tax_id', string='Impuestos de venta por defecto',
        domain=[('type_tax_use', '=', 'sale')], help='Medicamentos: IVA 0%.')
    biotex_product_total = fields.Integer(compute='_compute_biotex_stats')
    biotex_product_complete = fields.Integer(compute='_compute_biotex_stats')
    biotex_product_pending = fields.Integer(compute='_compute_biotex_stats')

    @api.depends('biotex_group_id.code', 'biotex_code')
    def _compute_composite(self):
        for c in self:
            c.biotex_composite = '%s-%s' % (c.biotex_group_id.code, c.biotex_code) if c.biotex_group_id and c.biotex_code else False

    @api.depends('biotex_group_id')
    def _compute_level(self):
        for c in self:
            c.biotex_level = 'family' if c.biotex_group_id else 'other'

    @api.depends('name', 'biotex_composite')
    def _compute_display_name(self):
        for c in self:
            c.display_name = '%s · %s' % (c.biotex_composite, c.name) if c.biotex_composite else c.complete_name

    def _compute_biotex_stats(self):
        Product = self.env['product.template']
        for categ in self:
            products = Product.search([('categ_id', 'child_of', categ.id)])
            categ.biotex_product_total = len(products)
            categ.biotex_product_complete = len(products.filtered(lambda p: p.biotex_class_state == 'complete'))
            categ.biotex_product_pending = categ.biotex_product_total - categ.biotex_product_complete

    @api.constrains('biotex_code', 'biotex_group_id', 'biotex_classifier_ids')
    def _check_family(self):
        for c in self:
            if not c.biotex_group_id:
                continue
            if not re.fullmatch(r'[A-Z0-9]{3}', c.biotex_code or ''):
                raise ValidationError('El código de familia son 3 caracteres en mayúsculas (ej. EDO, GAS).')
            if self.search_count([('biotex_code', '=', c.biotex_code), ('biotex_group_id', '=', c.biotex_group_id.id), ('id', '!=', c.id)]):
                raise ValidationError('Ya existe la familia %s en el grupo %s.' % (c.biotex_code, c.biotex_group_id.code))
            bad = c.biotex_classifier_ids.filtered(lambda k: k.group_id != c.biotex_group_id)
            if bad:
                raise ValidationError('Los clasificadores %s no pertenecen al grupo %s.' % (', '.join(bad.mapped('code')), c.biotex_group_id.code))

    # ---- permisos: familias solo Dirección (regla 9) ----
    def _biotex_check_direction(self):
        if self.env.su or self.env.context.get('biotex_skip_direction_check'):
            return
        if not self.env.user.has_group('biotex_base.group_biotex_direction'):
            raise AccessError('Solo Dirección puede crear o modificar familias del catálogo.')

    @api.model_create_multi
    def create(self, vals_list):
        self._biotex_check_direction()
        return super().create(vals_list)

    def write(self, vals):
        self._biotex_check_direction()
        return super().write(vals)

    def action_open_reorder_wizard(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Reordenar consecutivos por medida', 'res_model': 'biotex.reorder.wizard',
                'view_mode': 'form', 'target': 'new', 'context': {'default_family_id': self.id}}

    def action_view_pending(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Pendientes de clasificar: %s' % self.name, 'res_model': 'product.template',
                'view_mode': 'list,kanban,form', 'domain': [('categ_id', 'child_of', self.id), ('biotex_class_state', '!=', 'complete')]}

    @api.model
    def biotex_get_tree(self):
        """Grupos → familias → clasificadores autorizados, para el asistente OWL."""
        result = []
        for g in self.env['biotex.group'].search([]):
            fams = []
            for f in g.family_ids.sorted('name'):
                fams.append({
                    'id': f.id, 'name': f.name, 'code': f.biotex_code, 'composite': f.biotex_composite, 'status': f.biotex_status,
                    'hint': f.biotex_description_hint or '', 'photo_required': f.biotex_photo_required, 'pending': f.biotex_product_pending,
                    'classifiers': [{'id': k.id, 'code': k.code, 'name': k.name, 'status': k.status} for k in f.biotex_classifier_ids.sorted('code')],
                })
            result.append({'id': g.id, 'code': g.code, 'name': g.name, 'axis': g.classifier_axis or '', 'division': g.division_id.name,
                           'regulated': g.regulated, 'color': g.color, 'families': fams})
        return result
