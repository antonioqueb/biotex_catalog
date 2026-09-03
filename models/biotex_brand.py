import re
import unicodedata

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def normalize_brand(name):
    """Normaliza para detectar duplicados: sin acentos, sin espacios ni puntuación, minúsculas."""
    if not name:
        return ''
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    name = re.sub(r'[^a-z0-9]', '', name.lower())
    # abreviaturas frecuentes
    for suffix in ('sadecv', 'sa', 'inc', 'ltd', 'corp', 'co', 'llc'):
        if name.endswith(suffix) and len(name) > len(suffix) + 2:
            name = name[: -len(suffix)]
    return name


class BiotexBrand(models.Model):
    """Marcas: abiertas a cualquier usuario con validación de duplicados (R03)."""
    _name = 'biotex.brand'
    _description = 'Marca'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    normalized_name = fields.Char(compute='_compute_normalized_name', store=True, index=True)
    manufacturer_id = fields.Many2one('res.partner', string='Fabricante')
    logo = fields.Image(max_width=256, max_height=256)
    active = fields.Boolean(default=True)
    notes = fields.Text()
    product_count = fields.Integer(compute='_compute_product_count')
    created_by_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)

    @api.depends('name')
    def _compute_normalized_name(self):
        for brand in self:
            brand.normalized_name = normalize_brand(brand.name)

    def _compute_product_count(self):
        data = self.env['product.template']._read_group(
            [('biotex_brand_id', 'in', self.ids)], ['biotex_brand_id'], ['__count'])
        counts = {brand.id: count for brand, count in data}
        for brand in self:
            brand.product_count = counts.get(brand.id, 0)

    @api.constrains('name')
    def _check_duplicate(self):
        for brand in self:
            dup = self.search([
                ('normalized_name', '=', normalize_brand(brand.name)),
                ('id', '!=', brand.id), '|', ('active', '=', True), ('active', '=', False)], limit=1)
            if dup:
                raise ValidationError(
                    'La marca "%s" ya existe como "%s" (misma escritura sin espacios/abreviaturas). '
                    'Use la existente.' % (brand.name, dup.name))

    @api.model
    def find_similar(self, name):
        """Usado por el asistente: regresa posibles duplicados antes de crear."""
        norm = normalize_brand(name)
        if not norm:
            return []
        brands = self.search(['|', ('normalized_name', '=', norm), ('normalized_name', 'ilike', norm[:4])], limit=8)
        return [{'id': b.id, 'name': b.name, 'exact': b.normalized_name == norm} for b in brands]

    @api.model
    def name_create(self, name):
        name = (name or '').strip()
        existing = self.search([('normalized_name', '=', normalize_brand(name))], limit=1)
        if existing:
            return existing.id, existing.display_name
        return super().name_create(name)

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Productos %s' % self.name,
            'res_model': 'product.template',
            'view_mode': 'kanban,list,form',
            'domain': [('biotex_brand_id', '=', self.id)],
            'context': {'default_biotex_brand_id': self.id},
        }
