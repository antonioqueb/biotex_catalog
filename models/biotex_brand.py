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
    for suffix in ('sadecv', 'sa', 'inc', 'ltd', 'corp', 'co', 'llc'):
        if name.endswith(suffix) and len(name) > len(suffix) + 2:
            name = name[: -len(suffix)]
    return name


def suggest_code(name):
    """Código de 4 caracteres a partir del nombre: consonantes primero (3M -> 3M3M, KENDALL -> KDLL)."""
    base = re.sub(r'[^A-Z0-9]', '', unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().upper())
    if not base:
        return ''
    if len(base) <= 4:
        return (base * 4)[:4]
    cons = base[0] + re.sub(r'[AEIOU]', '', base[1:])
    return (cons if len(cons) >= 4 else base)[:4]


class BiotexBrand(models.Model):
    """Marcas: atributo comercial (segmento MMMM de la clave), abiertas a cualquier usuario con validación de duplicados (R03)."""
    _name = 'biotex.brand'
    _description = 'Marca'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    code = fields.Char(string='Código', size=4, required=True, index=True, help='4 caracteres en mayúsculas; segmento MMMM de la clave.')
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

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for b in self:
            b.display_name = '%s · %s' % (b.code, b.name) if b.code else b.name

    def _compute_product_count(self):
        data = self.env['product.template']._read_group([('biotex_brand_id', 'in', self.ids)], ['biotex_brand_id'], ['__count'])
        counts = {brand.id: count for brand, count in data}
        for brand in self:
            brand.product_count = counts.get(brand.id, 0)

    @api.onchange('name')
    def _onchange_name_code(self):
        for b in self:
            if b.name and not b.code:
                b.code = suggest_code(b.name)

    @api.constrains('name', 'code')
    def _check_duplicate(self):
        for brand in self:
            if not re.fullmatch(r'[A-Z0-9]{4}', brand.code or ''):
                raise ValidationError('El código de marca son exactamente 4 caracteres en mayúsculas (ej. LGMD, 3M3M).')
            dup = self.search([('normalized_name', '=', normalize_brand(brand.name)), ('id', '!=', brand.id), '|', ('active', '=', True), ('active', '=', False)], limit=1)
            if dup:
                raise ValidationError('La marca "%s" ya existe como "%s" (misma escritura sin espacios/abreviaturas). Use la existente.' % (brand.name, dup.name))
            if self.search_count([('code', '=', brand.code), ('id', '!=', brand.id), '|', ('active', '=', True), ('active', '=', False)]):
                raise ValidationError('El código de marca %s ya está en uso.' % brand.code)

    @api.model
    def find_similar(self, name):
        norm = normalize_brand(name)
        if not norm:
            return []
        brands = self.search(['|', ('normalized_name', '=', norm), ('normalized_name', 'ilike', norm[:4])], limit=8)
        return [{'id': b.id, 'name': b.name, 'code': b.code, 'exact': b.normalized_name == norm} for b in brands]

    @api.model
    def suggest_code(self, name):
        code = suggest_code(name)
        i = 0
        while self.search_count([('code', '=', code)]):
            i += 1
            code = code[:3] + str(i)
        return code

    @api.model
    def name_create(self, name):
        name = (name or '').strip()
        existing = self.search([('normalized_name', '=', normalize_brand(name))], limit=1)
        if existing:
            return existing.id, existing.display_name
        rec = self.create({'name': name, 'code': self.suggest_code(name)})
        return rec.id, rec.display_name

    def action_view_products(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Productos %s' % self.name, 'res_model': 'product.template',
                'view_mode': 'kanban,list,form', 'domain': [('biotex_brand_id', '=', self.id)], 'context': {'default_biotex_brand_id': self.id}}
