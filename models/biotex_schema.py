"""Esquema de clasificación v2: División > Grupo > Familia > Clasificador, con Marca como atributo.

Clave comercial  GG-MMMM-FFF-CCC-NN   (ej. CE-LGMD-EDO-EKG-01)
Clave de genérico G-GG-FFF-CCC-NNN    (ej. G-CE-EDO-EKG-001)

El grupo no es un nivel de categoría: se muestra como etiqueta del producto (product.tag sincronizada)
para no saturar el árbol de categorías, que queda plano con solo las familias.
"""
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class BiotexDivision(models.Model):
    _name = 'biotex.division'
    _description = 'División (naturaleza contable)'
    _order = 'code'

    code = fields.Char(required=True, size=3)
    name = fields.Char(required=True)
    accounting_nature = fields.Char(string='Naturaleza contable')
    inventory_policy = fields.Char(string='Política de inventario')
    group_ids = fields.One2many('biotex.group', 'division_id', string='Grupos')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s · %s' % (r.code, r.name)


class BiotexGroup(models.Model):
    """Grupo (2 letras). Define el eje del clasificador y si el producto está regulado por COFEPRIS."""
    _name = 'biotex.group'
    _description = 'Grupo de catálogo'
    _order = 'sequence, code'

    code = fields.Char(required=True, size=2)
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    division_id = fields.Many2one('biotex.division', string='División', required=True)
    regulated = fields.Boolean(string='Regulado por COFEPRIS')
    classifier_axis = fields.Char(string='Eje del clasificador', help='Qué significa el clasificador en este grupo: equipo destino, tipo de artículo, forma farmacéutica...')
    note = fields.Text()
    color = fields.Integer(default=0)
    active = fields.Boolean(default=True)
    tag_id = fields.Many2one('product.tag', string='Etiqueta de producto', readonly=True, copy=False)
    family_ids = fields.One2many('product.category', 'biotex_group_id', string='Familias')
    classifier_ids = fields.One2many('biotex.classifier', 'group_id', string='Clasificadores')
    family_count = fields.Integer(compute='_compute_counts')
    classifier_count = fields.Integer(compute='_compute_counts')
    product_count = fields.Integer(compute='_compute_counts')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s · %s' % (r.code, r.name)

    def _compute_counts(self):
        Product = self.env['product.template']
        for g in self:
            g.family_count = len(g.family_ids)
            g.classifier_count = len(g.classifier_ids)
            g.product_count = Product.search_count([('biotex_group_id', '=', g.id)])

    @api.constrains('code')
    def _check_code(self):
        for g in self:
            if not re.fullmatch(r'[A-Z]{2}', g.code or ''):
                raise ValidationError('El código de grupo son 2 letras mayúsculas (ej. CE, MC, MT).')
            if self.search_count([('code', '=', g.code), ('id', '!=', g.id)]):
                raise ValidationError('Ya existe el grupo %s.' % g.code)

    def _ensure_tag(self):
        Tag = self.env['product.tag'].sudo()
        for g in self:
            if not g.tag_id:
                g.tag_id = Tag.search([('name', '=', '%s · %s' % (g.code, g.name))], limit=1) or Tag.create({'name': '%s · %s' % (g.code, g.name), 'color': g.color})
            elif g.tag_id.name != '%s · %s' % (g.code, g.name) or g.tag_id.color != g.color:
                g.tag_id.write({'name': '%s · %s' % (g.code, g.name), 'color': g.color})

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        groups._ensure_tag()
        return groups

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'code', 'color'} & set(vals):
            self._ensure_tag()
        return res

    def action_view_products(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Productos %s' % self.code, 'res_model': 'product.template',
                'view_mode': 'list,kanban,form', 'domain': [('biotex_group_id', '=', self.id)], 'context': {'search_default_group_biotex_family': 1}}


class BiotexClassifier(models.Model):
    """Clasificador (3 letras). Alcance = grupo: el mismo código puede existir en dos grupos con distinto significado."""
    _name = 'biotex.classifier'
    _description = 'Clasificador'
    _order = 'group_id, code'

    code = fields.Char(required=True, size=3)
    name = fields.Char(required=True)
    group_id = fields.Many2one('biotex.group', required=True, ondelete='cascade')
    axis = fields.Char(related='group_id.classifier_axis', string='Eje')
    status = fields.Selection([('active', 'Activo'), ('pending', 'Pendiente de definir'), ('proposed', 'Propuesta')], default='active', required=True)
    family_ids = fields.Many2many('product.category', 'biotex_family_classifier_rel', 'classifier_id', 'family_id', string='Familias autorizadas')
    composite = fields.Char(compute='_compute_composite', store=True, string='Clave compuesta')
    product_count = fields.Integer(compute='_compute_product_count')
    active = fields.Boolean(default=True)

    @api.depends('group_id.code', 'code')
    def _compute_composite(self):
        for c in self:
            c.composite = '%s-%s' % (c.group_id.code or '', c.code or '')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for c in self:
            c.display_name = '%s · %s' % (c.code, c.name)

    def _compute_product_count(self):
        for c in self:
            c.product_count = self.env['product.template'].search_count([('biotex_classifier_id', '=', c.id)])

    @api.constrains('code', 'group_id')
    def _check_code(self):
        for c in self:
            if not re.fullmatch(r'[A-Z0-9]{3}', c.code or ''):
                raise ValidationError('El clasificador son 3 caracteres en mayúsculas (ej. EKG, GAS, TAB).')
            if self.search_count([('code', '=', c.code), ('group_id', '=', c.group_id.id), ('id', '!=', c.id)]):
                raise ValidationError('Ya existe el clasificador %s en el grupo %s.' % (c.code, c.group_id.code))


class BiotexSpecialty(models.Model):
    """Servicio clínico que consume el producto (N:M)."""
    _name = 'biotex.specialty'
    _description = 'Especialidad clínica'
    _order = 'name'

    code = fields.Char(required=True, size=3)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s · %s' % (r.code, r.name)


class BiotexMtSubclass(models.Model):
    """Subclase terapéutica de medicamento: atributo del producto, no nivel de la clave."""
    _name = 'biotex.mt.subclass'
    _description = 'Subclase terapéutica'
    _order = 'family_id, code'

    code = fields.Char(required=True, size=3)
    name = fields.Char(required=True)
    family_id = fields.Many2one('product.category', string='Familia (MT)', required=True, domain=[('biotex_group_id.code', '=', 'MT')])

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s · %s' % (r.code, r.name)


class BiotexGeneric(models.Model):
    """Producto genérico: agrupa las marcas equivalentes de un mismo artículo. Clave G-GG-FFF-CCC-NNN."""
    _name = 'biotex.generic'
    _description = 'Producto genérico'
    _order = 'code'

    code = fields.Char(readonly=True, copy=False, index=True)
    name = fields.Char(string='Descripción genérica', required=True)
    family_id = fields.Many2one('product.category', string='Familia', required=True, domain=[('biotex_level', '=', 'family')])
    group_id = fields.Many2one(related='family_id.biotex_group_id', store=True)
    classifier_id = fields.Many2one('biotex.classifier', string='Clasificador', required=True)
    measure = fields.Char(string='Medida')
    consecutive = fields.Integer(readonly=True)
    product_ids = fields.One2many('product.template', 'biotex_generic_id', string='Presentaciones por marca')
    product_count = fields.Integer(compute='_compute_product_count')
    notes = fields.Text()

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s · %s' % (r.code or 'nuevo', r.name)

    def _compute_product_count(self):
        for g in self:
            g.product_count = len(g.product_ids)

    @api.constrains('family_id', 'classifier_id')
    def _check_pair(self):
        for g in self:
            if g.classifier_id and g.family_id and g.classifier_id not in g.family_id.biotex_classifier_ids:
                raise ValidationError('El clasificador %s no está autorizado para la familia %s.' % (g.classifier_id.code, g.family_id.biotex_composite))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for g in records:
            if not g.code:
                prefix = 'G-%s-%s-%s-' % (g.group_id.code, g.family_id.biotex_code, g.classifier_id.code)
                last = self.search([('code', '=like', prefix + '%'), ('id', '!=', g.id)], order='consecutive desc', limit=1)
                g.consecutive = (last.consecutive or 0) + 1
                g.code = '%s%03d' % (prefix, g.consecutive)
        return records

    @api.model
    def find_or_create(self, family, classifier, name, measure=None):
        """Localiza el genérico por familia + clasificador + descripción normalizada (sin marca)."""
        norm = re.sub(r'[^a-z0-9]', '', (name or '').lower())
        for g in self.search([('family_id', '=', family.id), ('classifier_id', '=', classifier.id)]):
            if re.sub(r'[^a-z0-9]', '', g.name.lower()) == norm and (g.measure or '') == (measure or ''):
                return g
        return self.create({'name': name, 'family_id': family.id, 'classifier_id': classifier.id, 'measure': measure or False})


class BiotexPackageType(models.Model):
    """Tipo de empaque: catálogo configurable (pieza, sobre, caja, bolsa, paquete...).

    Odoo no trae un catálogo equivalente: `stock.package.type` describe embalaje logístico
    con dimensiones para envío, no la presentación comercial del insumo.
    """
    _name = 'biotex.package.type'
    _description = 'Tipo de empaque'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char(size=8)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique(name)', 'Ya existe un tipo de empaque con ese nombre.')

    @api.model
    def resolve(self, label):
        """Devuelve el tipo por nombre, creándolo si el catálogo aún no lo tiene (carga de datos)."""
        label = (label or '').strip()
        if not label:
            return self.browse()
        return self.search([('name', '=ilike', label)], limit=1) or self.create({'name': label.capitalize()})
