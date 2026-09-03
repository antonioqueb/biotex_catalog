import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ProductCategory(models.Model):
    """Grupo (nivel 1) -> Familia (nivel 2). Las familias solo las define Dirección."""
    _inherit = 'product.category'

    biotex_level = fields.Selection([
        ('root', 'Raíz'), ('group', 'Grupo'), ('family', 'Familia'), ('other', 'Otro')],
        compute='_compute_biotex_level', store=True)
    biotex_code = fields.Char(
        string='Código', size=6,
        help='Prefijo de la clave. Grupo: CON, MED, INS, EQM. Familia: MAS, AGU...')
    biotex_sequence_id = fields.Many2one('ir.sequence', string='Secuencia de claves', copy=False, readonly=True)
    biotex_photo_required = fields.Boolean(string='Foto obligatoria', default=True)
    biotex_description_hint = fields.Char(
        string='Estructura de descripción',
        help='Ej. "Aguja hipodérmica + calibre + longitud + presentación". Se muestra en el asistente.')
    biotex_default_tax_ids = fields.Many2many(
        'account.tax', 'biotex_categ_tax_rel', 'categ_id', 'tax_id',
        string='Impuestos de venta por defecto', domain=[('type_tax_use', '=', 'sale')],
        help='Medicamentos: IVA 0%.')
    biotex_secondary_group_ids = fields.Many2many(
        'product.category', 'biotex_categ_secondary_group_rel', 'family_id', 'group_id',
        string='Grupos adicionales', domain=[('biotex_level', '=', 'group')],
        help='Una familia puede pertenecer a dos grupos (microondas de cocina vs. laboratorio).')
    biotex_product_total = fields.Integer(compute='_compute_biotex_stats')
    biotex_product_complete = fields.Integer(compute='_compute_biotex_stats')
    biotex_product_pending = fields.Integer(compute='_compute_biotex_stats')

    @api.depends('parent_id', 'parent_id.parent_id')
    def _compute_biotex_level(self):
        for categ in self:
            depth = 0
            node = categ.parent_id
            while node:
                depth += 1
                node = node.parent_id
            categ.biotex_level = {0: 'root', 1: 'group', 2: 'family'}.get(depth, 'other')

    def _compute_biotex_stats(self):
        Product = self.env['product.template']
        for categ in self:
            products = Product.search([('categ_id', 'child_of', categ.id)])
            categ.biotex_product_total = len(products)
            categ.biotex_product_complete = len(products.filtered(lambda p: p.biotex_class_state == 'complete'))
            categ.biotex_product_pending = categ.biotex_product_total - categ.biotex_product_complete

    @api.constrains('biotex_code', 'parent_id')
    def _check_code(self):
        for categ in self:
            if categ.biotex_level in ('group', 'family') and not categ.biotex_code:
                raise ValidationError('Grupos y familias requieren un código corto (ej. CON, MAS).')
            if categ.biotex_code and not re.fullmatch(r'[A-Z0-9]{2,6}', categ.biotex_code):
                raise ValidationError('El código debe ser de 2 a 6 caracteres en mayúsculas sin espacios.')
            if categ.biotex_code:
                dup = self.search([('biotex_code', '=', categ.biotex_code), ('parent_id', '=', categ.parent_id.id),
                                   ('id', '!=', categ.id)], limit=1)
                if dup:
                    raise ValidationError('Ya existe "%s" con el código %s bajo el mismo grupo.' % (dup.name, categ.biotex_code))

    # ---- permisos: familias solo Dirección (regla 9) ----
    def _biotex_check_direction(self):
        if self.env.su or self.env.context.get('biotex_skip_direction_check'):
            return
        if not self.env.user.has_group('biotex_base.group_biotex_direction'):
            raise AccessError('Solo Dirección puede crear o modificar grupos y familias del catálogo.')

    @api.model_create_multi
    def create(self, vals_list):
        self._biotex_check_direction()
        records = super().create(vals_list)
        records._biotex_ensure_sequence()
        return records

    def write(self, vals):
        self._biotex_check_direction()
        res = super().write(vals)
        if 'biotex_code' in vals or 'parent_id' in vals:
            self._biotex_ensure_sequence()
        return res

    def _biotex_ensure_sequence(self):
        Seq = self.env['ir.sequence'].sudo()
        for family in self.filtered(lambda c: c.biotex_level == 'family' and c.biotex_code):
            prefix = '%s-%s-' % (family.parent_id.biotex_code or 'XXX', family.biotex_code)
            if family.biotex_sequence_id:
                family.biotex_sequence_id.prefix = prefix
            else:
                family.biotex_sequence_id = Seq.create({
                    'name': 'Claves %s' % family.complete_name,
                    'code': 'biotex.clave.%s' % family.id,
                    'prefix': prefix,
                    'padding': 4,
                    'implementation': 'no_gap',
                })

    def biotex_next_clave(self):
        self.ensure_one()
        if self.biotex_level != 'family':
            raise ValidationError('Solo se asignan claves dentro de una familia.')
        if not self.biotex_sequence_id:
            self.sudo()._biotex_ensure_sequence()
        return self.biotex_sequence_id.sudo().next_by_id()

    def action_open_reorder_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reordenar consecutivos por medida',
            'res_model': 'biotex.reorder.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_family_id': self.id},
        }

    def action_view_pending(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pendientes de clasificar: %s' % self.name,
            'res_model': 'product.template',
            'view_mode': 'list,kanban,form',
            'domain': [('categ_id', 'child_of', self.id), ('biotex_class_state', '!=', 'complete')],
        }

    @api.model
    def biotex_get_tree(self):
        """Árbol grupo -> familias para el asistente OWL."""
        groups = self.search([('biotex_level', '=', 'group')], order='name')
        result = []
        for g in groups:
            families = self.search([
                '|', ('parent_id', '=', g.id), ('biotex_secondary_group_ids', 'in', g.id),
                ('biotex_level', '=', 'family')], order='name')
            result.append({
                'id': g.id, 'name': g.name, 'code': g.biotex_code,
                'families': [{
                    'id': f.id, 'name': f.name, 'code': f.biotex_code,
                    'hint': f.biotex_description_hint or '',
                    'photo_required': f.biotex_photo_required,
                    'pending': f.biotex_product_pending,
                } for f in families],
            })
        return result
