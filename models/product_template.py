import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # --- clasificación (la clave manda: GG-MMMM-FFF-CCC-NN) ---
    biotex_family_id = fields.Many2one(
        'product.category', string='Familia', domain=[('biotex_level', '=', 'family')],
        compute='_compute_biotex_family', inverse='_inverse_biotex_family', store=True)
    biotex_group_id = fields.Many2one('biotex.group', string='Grupo', related='categ_id.biotex_group_id', store=True, index=True)
    biotex_division_id = fields.Many2one('biotex.division', string='División', related='categ_id.biotex_group_id.division_id', store=True)
    biotex_classifier_id = fields.Many2one(
        'biotex.classifier', string='Clasificador', index=True,
        domain="[('id', 'in', biotex_allowed_classifier_ids)]")
    biotex_allowed_classifier_ids = fields.Many2many('biotex.classifier', compute='_compute_allowed_classifiers')
    biotex_classifier_axis = fields.Char(related='biotex_group_id.classifier_axis', string='Eje del clasificador')
    biotex_brand_id = fields.Many2one('biotex.brand', string='Marca', index=True)
    biotex_brand_code = fields.Char(related='biotex_brand_id.code')
    biotex_consecutive = fields.Integer(string='Consecutivo', readonly=True, copy=False)
    biotex_generic_id = fields.Many2one('biotex.generic', string='Genérico', index=True, help='Agrupa las marcas equivalentes del mismo artículo (clave G-GG-FFF-CCC-NNN).')
    biotex_subclass_id = fields.Many2one('biotex.mt.subclass', string='Subclase terapéutica', domain="[('family_id', '=', categ_id)]")
    biotex_regulated = fields.Boolean(related='biotex_group_id.regulated', string='Regulado COFEPRIS')

    # --- descripción estructurada: descripción + medidas + unidad indivisible ---
    biotex_name = fields.Char(string='Descripción', help='Ej. "Electrodo de broche para ECG redondo autoadherible". Sin marca ni medida.')
    biotex_measure = fields.Char(string='Medidas', help='Ej. 36 mm x 44 mm; 21G x 32 mm; 5 ml.')
    biotex_measure_value = fields.Float(string='Medida numérica', compute='_compute_measure_value', store=True)
    biotex_content = fields.Char(string='Unidad indivisible (UI)', help='Presentación mínima de venta. Ej. "Bolsa con 50", "Pieza", "Sobre con 1".')
    biotex_package_type_id = fields.Many2one('biotex.package.type', string='Tipo de empaque', ondelete='restrict')
    biotex_package_qty = fields.Float(string='Cantidad por presentación', default=1.0)

    # --- identificación ---
    biotex_reference = fields.Char(string='Referencia del fabricante', index=True, copy=False, help='Identificador primario (regla 1). No se repite.')
    biotex_own_code = fields.Boolean(string='Código propio', compute='_compute_own_code', store=True)
    biotex_model = fields.Char(string='Modelo')
    biotex_manufacturer_id = fields.Many2one('res.partner', string='Fabricante')
    biotex_country_id = fields.Many2one('res.country', string='País de origen')
    biotex_primary_distributor_id = fields.Many2one('res.partner', string='Distribuidor primario', domain=[('supplier_rank', '>', 0)])
    biotex_alt_code = fields.Char(string='Clave alterna', help='Clave del cliente, SAI o del proveedor.')
    biotex_legacy_code = fields.Char(string='Clave anterior (SICAR)')
    biotex_characteristics = fields.Text(string='Características')
    biotex_usage_notes = fields.Char(string='Notas de uso')

    # --- uso clínico ---
    biotex_specialty_ids = fields.Many2many('biotex.specialty', 'biotex_product_specialty_rel', 'product_tmpl_id', 'specialty_id', string='Especialidades')
    biotex_main_specialty_id = fields.Many2one('biotex.specialty', string='Especialidad principal')
    biotex_equipment_ids = fields.Many2many('biotex.equipment', 'biotex_product_equipment_rel', 'product_tmpl_id', 'equipment_id', string='Equipos relacionados')
    biotex_main_equipment_id = fields.Many2one('biotex.equipment', string='Equipo principal')
    biotex_synonym_ids = fields.One2many('biotex.product.synonym', 'product_tmpl_id', string='Sinónimos')
    biotex_high_rotation = fields.Boolean(string='Alta rotación', help='Solo alta rotación lleva stock mínimo (regla 7).')

    # --- niveles de precio (Precio 1 = precio de lista) ---
    biotex_price_2 = fields.Float(string='Precio 2', digits='Product Price')
    biotex_wholesale_2 = fields.Float(string='Mayoreo 2 (desde)', help='Cantidad a partir de la cual aplica el precio 2.')
    biotex_price_3 = fields.Float(string='Precio 3', digits='Product Price')
    biotex_wholesale_3 = fields.Float(string='Mayoreo 3 (desde)')
    biotex_price_4 = fields.Float(string='Precio 4', digits='Product Price')
    biotex_wholesale_4 = fields.Float(string='Mayoreo 4 (desde)')

    # --- fotos (hasta 3) ---
    biotex_image_2 = fields.Image(string='Foto 2', max_width=1920, max_height=1920)
    biotex_image_3 = fields.Image(string='Foto 3', max_width=1920, max_height=1920)
    biotex_photo_count = fields.Integer(compute='_compute_class_state', store=True)
    biotex_photo_waived = fields.Boolean(string='Completo sin foto (autorizado)', tracking=True, help='Solo Dirección (regla 10).')

    # --- estado de clasificación ---
    biotex_class_state = fields.Selection([
        ('unclassified', 'Sin clasificar'), ('no_photo', 'Clasificado sin foto'), ('complete', 'Completo')],
        string='Clasificación', compute='_compute_class_state', store=True, index=True)
    biotex_missing = fields.Char(string='Faltantes', compute='_compute_class_state', store=True)

    # ------------------------------------------------------------------ computes
    @api.depends('biotex_measure')
    def _compute_measure_value(self):
        for p in self:
            m = re.search(r'\d+(?:[.,]\d+)?', p.biotex_measure or '')
            p.biotex_measure_value = float(m.group().replace(',', '.')) if m else 0.0

    @api.depends('categ_id', 'categ_id.biotex_level')
    def _compute_biotex_family(self):
        for p in self:
            p.biotex_family_id = p.categ_id if p.categ_id.biotex_level == 'family' else False

    def _inverse_biotex_family(self):
        for p in self:
            if p.biotex_family_id:
                p.categ_id = p.biotex_family_id

    @api.depends('categ_id.biotex_classifier_ids')
    def _compute_allowed_classifiers(self):
        for p in self:
            p.biotex_allowed_classifier_ids = p.categ_id.biotex_classifier_ids

    @api.depends('biotex_reference', 'barcode')
    def _compute_own_code(self):
        for p in self:
            p.biotex_own_code = not p.biotex_reference and not p.barcode

    @api.depends('categ_id', 'biotex_classifier_id', 'default_code', 'biotex_name', 'biotex_measure', 'biotex_brand_id',
                 'image_1920', 'biotex_image_2', 'biotex_image_3', 'biotex_photo_waived', 'categ_id.biotex_photo_required')
    def _compute_class_state(self):
        for p in self:
            photos = sum(1 for img in (p.image_1920, p.biotex_image_2, p.biotex_image_3) if img)
            p.biotex_photo_count = photos
            missing = []
            if p.categ_id.biotex_level != 'family':
                missing.append('familia')
            if not p.biotex_classifier_id:
                missing.append('clasificador')
            if not p.biotex_brand_id:
                missing.append('marca')
            if not p.default_code:
                missing.append('clave')
            if not p.biotex_name:
                missing.append('descripción')
            if not p.biotex_measure:
                missing.append('medidas')
            if missing:
                p.biotex_class_state = 'unclassified'
            elif photos == 0 and p.categ_id.biotex_photo_required and not p.biotex_photo_waived:
                p.biotex_class_state = 'no_photo'
                missing.append('foto')
            else:
                p.biotex_class_state = 'complete'
            p.biotex_missing = ', '.join(missing)

    # ------------------------------------------------------------------ etiqueta de grupo sincronizada
    def _biotex_sync_group_tag(self):
        group_tags = self.env['biotex.group'].sudo().search([]).mapped('tag_id')
        for p in self:
            tag = p.biotex_group_id.tag_id
            tags = p.product_tag_ids - group_tags
            if tag:
                tags |= tag
            if tags != p.product_tag_ids:
                p.product_tag_ids = [(6, 0, tags.ids)]

    # ------------------------------------------------------------------ onchange / constraints
    @api.onchange('biotex_name', 'biotex_measure', 'biotex_content')
    def _onchange_structured_description(self):
        for p in self:
            if p.biotex_name:
                p.name = p._biotex_build_name()

    def _biotex_build_name(self):
        self.ensure_one()
        return ' '.join(x.strip() for x in (self.biotex_name, self.biotex_measure, self.biotex_content) if x)

    @api.onchange('categ_id')
    def _onchange_categ(self):
        for p in self:
            if p.categ_id.biotex_default_tax_ids:
                p.taxes_id = p.categ_id.biotex_default_tax_ids
            if p.biotex_classifier_id and p.biotex_classifier_id not in p.categ_id.biotex_classifier_ids:
                p.biotex_classifier_id = False

    @api.onchange('biotex_specialty_ids')
    def _onchange_specialties(self):
        for p in self:
            if p.biotex_specialty_ids and not p.biotex_main_specialty_id:
                p.biotex_main_specialty_id = p.biotex_specialty_ids[0]

    @api.onchange('biotex_equipment_ids')
    def _onchange_equipment(self):
        for p in self:
            if p.biotex_equipment_ids and not p.biotex_main_equipment_id:
                p.biotex_main_equipment_id = p.biotex_equipment_ids[0]

    @api.constrains('biotex_classifier_id', 'categ_id')
    def _check_classifier(self):
        for p in self:
            if p.biotex_classifier_id and p.categ_id.biotex_level == 'family' and p.biotex_classifier_id not in p.categ_id.biotex_classifier_ids:
                raise ValidationError('El clasificador %s no está autorizado para la familia %s (%s).' % (
                    p.biotex_classifier_id.code, p.categ_id.biotex_composite, p.categ_id.biotex_group_id.classifier_axis or ''))

    @api.constrains('biotex_reference')
    def _check_reference_unique(self):
        for p in self.filtered('biotex_reference'):
            dup = self.search([('biotex_reference', '=ilike', p.biotex_reference.strip()), ('id', '!=', p.id)], limit=1)
            if dup:
                raise ValidationError('La referencia del fabricante "%s" ya está asignada a "%s".' % (p.biotex_reference, dup.display_name))

    @api.constrains('biotex_photo_waived')
    def _check_photo_waived(self):
        if any(self.mapped('biotex_photo_waived')) and not self.env.user.has_group('biotex_base.group_biotex_direction') and not self.env.su:
            raise ValidationError('Solo Dirección puede autorizar un producto completo sin foto.')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._biotex_sync_group_tag()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'categ_id' in vals or 'biotex_family_id' in vals:
            self._biotex_sync_group_tag()
        return res

    # ------------------------------------------------------------------ clave
    def _biotex_clave_prefix(self):
        self.ensure_one()
        fam = self.categ_id
        if fam.biotex_level != 'family':
            raise UserError('"%s" debe tener familia antes de asignar clave.' % self.display_name)
        if not self.biotex_classifier_id:
            raise UserError('"%s" necesita clasificador (%s) antes de asignar clave.' % (self.display_name, fam.biotex_group_id.classifier_axis or 'eje del grupo'))
        if not self.biotex_brand_id or not self.biotex_brand_id.code:
            raise UserError('"%s" necesita marca con código de 4 letras antes de asignar clave.' % self.display_name)
        return '%s-%s-%s-%s-' % (fam.biotex_group_id.code, self.biotex_brand_id.code, fam.biotex_code, self.biotex_classifier_id.code)

    def biotex_preview_clave(self):
        self.ensure_one()
        prefix = self._biotex_clave_prefix()
        last = self.search([('default_code', '=like', prefix + '%'), ('id', '!=', self.id)], order='biotex_consecutive desc', limit=1)
        return '%s%02d' % (prefix, (last.biotex_consecutive or 0) + 1)

    def action_assign_clave(self):
        """Clave GG-MMMM-FFF-CCC-NN, código propio si no hay referencia ni barcode, y genérico."""
        for p in self:
            if p.default_code and p.biotex_consecutive:
                continue
            prefix = p._biotex_clave_prefix()
            last = self.search([('default_code', '=like', prefix + '%'), ('id', '!=', p.id)], order='biotex_consecutive desc', limit=1)
            n = (last.biotex_consecutive or 0) + 1
            vals = {'default_code': '%s%02d' % (prefix, n), 'biotex_consecutive': n}
            if not p.barcode and not p.biotex_reference:
                vals['barcode'] = vals['default_code']
            if p.biotex_name and not p.name:
                vals['name'] = p._biotex_build_name()
            if not p.biotex_generic_id and p.biotex_name:
                vals['biotex_generic_id'] = self.env['biotex.generic'].find_or_create(p.categ_id, p.biotex_classifier_id, p.biotex_name, p.biotex_measure).id
            p.write(vals)
        return True

    def action_open_classifier(self):
        return {'type': 'ir.actions.client', 'tag': 'biotex_catalog.classifier', 'name': 'Asistente de clasificación',
                'context': {'biotex_product_ids': self.ids}}

    def action_print_qr_label(self):
        return self.env.ref('biotex_catalog.action_report_product_label_qr').report_action(self)

    @api.model
    def biotex_classifier_save(self, product_id, vals):
        """Punto de entrada del asistente OWL: guarda, sincroniza etiqueta y asigna clave en una sola llamada."""
        product = self.browse(product_id) if product_id else self.new({})
        clean = {k: v for k, v in vals.items() if k in self._fields}
        if clean.get('biotex_family_id'):
            clean['categ_id'] = clean['biotex_family_id']
        if not product_id and not clean.get('name'):
            clean['name'] = ' '.join(x.strip() for x in (clean.get('biotex_name'), clean.get('biotex_measure'), clean.get('biotex_content')) if x) or 'Producto sin nombre'
        if product_id:
            product.write(clean)
        else:
            product = self.create(clean)
        if clean.get('biotex_name'):
            product.name = product._biotex_build_name()
        if product.categ_id.biotex_level == 'family' and product.biotex_classifier_id and product.biotex_brand_id and not product.default_code:
            product.action_assign_clave()
        return {'id': product.id, 'name': product.name, 'default_code': product.default_code, 'state': product.biotex_class_state,
                'missing': product.biotex_missing, 'generic': product.biotex_generic_id.code or ''}

    @api.model
    def biotex_classifier_preview(self, vals):
        """Vista previa de la clave y del genérico sin guardar."""
        fam = self.env['product.category'].browse(vals.get('biotex_family_id')) if vals.get('biotex_family_id') else self.env['product.category']
        cls = self.env['biotex.classifier'].browse(vals.get('biotex_classifier_id')) if vals.get('biotex_classifier_id') else self.env['biotex.classifier']
        brand = self.env['biotex.brand'].browse(vals.get('biotex_brand_id')) if vals.get('biotex_brand_id') else self.env['biotex.brand']
        if not (fam and cls and brand and brand.code):
            return {'clave': '', 'generic': ''}
        prefix = '%s-%s-%s-%s-' % (fam.biotex_group_id.code, brand.code, fam.biotex_code, cls.code)
        last = self.search([('default_code', '=like', prefix + '%')], order='biotex_consecutive desc', limit=1)
        exclude = vals.get('id')
        if exclude and last.id == exclude:
            return {'clave': last.default_code, 'generic': last.biotex_generic_id.code or ''}
        gprefix = 'G-%s-%s-%s-' % (fam.biotex_group_id.code, fam.biotex_code, cls.code)
        return {'clave': '%s%02d' % (prefix, (last.biotex_consecutive or 0) + 1), 'generic': gprefix + '…'}

    @api.model
    def biotex_classifier_queue(self, product_ids=None, limit=200):
        domain = [('id', 'in', product_ids)] if product_ids else [('biotex_class_state', '!=', 'complete')]
        products = self.search(domain, limit=limit, order='biotex_class_state, write_date')
        return products.read([
            'name', 'default_code', 'biotex_name', 'biotex_measure', 'biotex_content', 'biotex_package_type_id', 'biotex_package_qty',
            'biotex_family_id', 'biotex_group_id', 'biotex_classifier_id', 'biotex_brand_id', 'biotex_model', 'biotex_manufacturer_id',
            'biotex_reference', 'biotex_country_id', 'biotex_primary_distributor_id', 'biotex_usage_notes', 'biotex_equipment_ids',
            'biotex_main_equipment_id', 'biotex_specialty_ids', 'biotex_main_specialty_id', 'biotex_class_state', 'biotex_missing',
            'biotex_photo_count', 'image_128', 'description', 'biotex_legacy_code'])

    # ------------------------------------------------------------------ búsqueda por sinónimo / referencia / marca / genérico
    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        res = super().name_search(name, domain, operator, limit)
        if name and operator in ('ilike', 'like', '=', '=ilike') and (not limit or len(res) < limit):
            extra = (Domain('biotex_synonym_ids.name', 'ilike', name) | Domain('biotex_reference', 'ilike', name)
                     | Domain('biotex_brand_id.name', 'ilike', name) | Domain('biotex_generic_id.code', 'ilike', name)
                     | Domain('biotex_alt_code', 'ilike', name) | Domain('biotex_legacy_code', 'ilike', name))
            found = [r[0] for r in res]
            records = self.search_fetch(Domain(domain or Domain.TRUE) & extra & Domain('id', 'not in', found), ['display_name'], limit=(limit - len(res)) if limit else None)
            res += [(r.id, r.display_name) for r in records]
        return res

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if value and operator in ('ilike', 'like', '=', '=ilike'):
            extra = Domain('biotex_synonym_ids.name', 'ilike', value) | Domain('biotex_reference', 'ilike', value) | Domain('biotex_brand_id.name', 'ilike', value)
            domain = Domain(domain) | extra
        return domain
