from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # --- descripción estructurada (nombre + medida + contenido) ---
    biotex_name = fields.Char(string='Nombre base', help='Ej. "Aguja hipodérmica". Sin marca ni medida.')
    biotex_measure = fields.Char(string='Medida / calibre', help='Ej. 21G x 32mm, 5 ml, adulto.')
    biotex_measure_value = fields.Float(
        string='Medida numérica', compute='_compute_measure_value', store=True,
        help='Primer número de la medida; se usa para reordenar consecutivos.')
    biotex_content = fields.Char(string='Contenido / presentación', help='Ej. Caja c/100, pieza, paquete c/10.')

    # --- identificación ---
    biotex_group_id = fields.Many2one('product.category', string='Grupo', compute='_compute_biotex_group', store=True)
    biotex_family_id = fields.Many2one(
        'product.category', string='Familia', domain=[('biotex_level', '=', 'family')],
        compute='_compute_biotex_family', inverse='_inverse_biotex_family', store=True)
    biotex_consecutive = fields.Integer(string='Consecutivo', readonly=True, copy=False)
    biotex_reference = fields.Char(
        string='Referencia del fabricante', index=True, copy=False,
        help='Identificador primario del producto (regla 1). No se repite. Si no existe, la empresa asigna código propio.')
    biotex_own_code = fields.Boolean(
        string='Código propio', compute='_compute_own_code', store=True,
        help='Producto sin código de fabricante ni código de barras: se etiqueta con la clave interna (QR).')
    biotex_brand_id = fields.Many2one('biotex.brand', string='Marca', index=True)
    biotex_model = fields.Char(string='Modelo')
    biotex_manufacturer_id = fields.Many2one('res.partner', string='Fabricante')
    biotex_equipment_ids = fields.Many2many(
        'biotex.equipment', 'biotex_product_equipment_rel', 'product_tmpl_id', 'equipment_id',
        string='Equipos compatibles')
    biotex_usage_notes = fields.Char(string='Notas de uso', help='Pediátrico, universal, estéril, desechable...')
    biotex_synonym_ids = fields.One2many('biotex.product.synonym', 'product_tmpl_id', string='Sinónimos')
    biotex_high_rotation = fields.Boolean(
        string='Alta rotación', help='Solo alta rotación lleva stock mínimo (regla 7).')

    # --- fotos (hasta 3) ---
    biotex_image_2 = fields.Image(string='Foto 2', max_width=1920, max_height=1920)
    biotex_image_3 = fields.Image(string='Foto 3', max_width=1920, max_height=1920)
    biotex_photo_count = fields.Integer(compute='_compute_class_state', store=True)
    biotex_photo_waived = fields.Boolean(
        string='Completo sin foto (autorizado)', tracking=True,
        help='Solo Dirección puede marcar completo un producto sin foto (regla 10).')

    # --- estado de clasificación ---
    biotex_class_state = fields.Selection([
        ('unclassified', 'Sin clasificar'),
        ('no_photo', 'Clasificado sin foto'),
        ('complete', 'Completo'),
    ], string='Clasificación', compute='_compute_class_state', store=True, index=True)
    biotex_missing = fields.Char(string='Faltantes', compute='_compute_class_state', store=True)

    # ------------------------------------------------------------------ computes
    @api.depends('biotex_measure')
    def _compute_measure_value(self):
        import re
        for p in self:
            m = re.search(r'\d+(?:[.,]\d+)?', p.biotex_measure or '')
            p.biotex_measure_value = float(m.group().replace(',', '.')) if m else 0.0

    @api.depends('categ_id', 'categ_id.parent_id', 'categ_id.biotex_level')
    def _compute_biotex_family(self):
        for p in self:
            p.biotex_family_id = p.categ_id if p.categ_id.biotex_level == 'family' else False

    def _inverse_biotex_family(self):
        for p in self:
            if p.biotex_family_id:
                p.categ_id = p.biotex_family_id

    @api.depends('categ_id', 'categ_id.parent_id')
    def _compute_biotex_group(self):
        for p in self:
            categ = p.categ_id
            p.biotex_group_id = categ.parent_id if categ.biotex_level == 'family' else (
                categ if categ.biotex_level == 'group' else False)

    @api.depends('biotex_reference', 'barcode')
    def _compute_own_code(self):
        for p in self:
            p.biotex_own_code = not p.biotex_reference and not p.barcode

    @api.depends('categ_id', 'default_code', 'biotex_name', 'biotex_measure', 'biotex_brand_id',
                 'image_1920', 'biotex_image_2', 'biotex_image_3', 'biotex_photo_waived',
                 'categ_id.biotex_photo_required')
    def _compute_class_state(self):
        for p in self:
            photos = sum(1 for img in (p.image_1920, p.biotex_image_2, p.biotex_image_3) if img)
            p.biotex_photo_count = photos
            missing = []
            if p.categ_id.biotex_level != 'family':
                missing.append('familia')
            if not p.default_code:
                missing.append('clave')
            if not p.biotex_name:
                missing.append('nombre base')
            if not p.biotex_measure:
                missing.append('medida')
            if not p.biotex_brand_id:
                missing.append('marca')
            if missing:
                p.biotex_class_state = 'unclassified'
            elif photos == 0 and p.categ_id.biotex_photo_required and not p.biotex_photo_waived:
                p.biotex_class_state = 'no_photo'
                missing.append('foto')
            else:
                p.biotex_class_state = 'complete'
            p.biotex_missing = ', '.join(missing)

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
    def _onchange_categ_taxes(self):
        for p in self:
            if p.categ_id.biotex_default_tax_ids:
                p.taxes_id = p.categ_id.biotex_default_tax_ids

    @api.constrains('biotex_reference')
    def _check_reference_unique(self):
        for p in self.filtered('biotex_reference'):
            dup = self.search([('biotex_reference', '=ilike', p.biotex_reference.strip()), ('id', '!=', p.id)], limit=1)
            if dup:
                raise ValidationError(
                    'La referencia del fabricante "%s" ya está asignada a "%s". La referencia no se repite entre productos.'
                    % (p.biotex_reference, dup.display_name))

    @api.constrains('biotex_photo_waived')
    def _check_photo_waived(self):
        if any(self.mapped('biotex_photo_waived')) and not self.env.user.has_group('biotex_base.group_biotex_direction') and not self.env.su:
            raise ValidationError('Solo Dirección puede autorizar un producto completo sin foto.')

    # ------------------------------------------------------------------ acciones
    def action_assign_clave(self):
        """Asigna clave GRUPO-FAMILIA-#### y código propio si no hay barcode."""
        for p in self:
            if p.default_code and p.biotex_consecutive:
                continue
            if p.categ_id.biotex_level != 'family':
                raise UserError('"%s" debe estar en una familia antes de asignar clave.' % p.display_name)
            clave = p.categ_id.biotex_next_clave()
            vals = {'default_code': clave, 'biotex_consecutive': int(clave.rsplit('-', 1)[-1])}
            if not p.barcode and not p.biotex_reference:
                vals['barcode'] = clave  # código propio (R05)
            if p.biotex_name and not p.name:
                vals['name'] = p._biotex_build_name()
            p.write(vals)
        return True

    def action_open_classifier(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'biotex_catalog.classifier',
            'name': 'Asistente de clasificación',
            'context': {'biotex_product_ids': self.ids},
        }

    def action_print_qr_label(self):
        return self.env.ref('biotex_catalog.action_report_product_label_qr').report_action(self)

    @api.model
    def biotex_classifier_save(self, product_id, vals):
        """Punto de entrada del asistente OWL: guarda y asigna clave en una sola llamada."""
        product = self.browse(product_id) if product_id else self.new({})
        clean = {k: v for k, v in vals.items() if k in self._fields}
        if clean.get('biotex_family_id'):
            clean['categ_id'] = clean['biotex_family_id']
        if not product_id and not clean.get('name'):
            clean['name'] = ' '.join(x.strip() for x in (
                clean.get('biotex_name'), clean.get('biotex_measure'), clean.get('biotex_content')) if x) or 'Producto sin nombre'
        if product_id:
            product.write(clean)
        else:
            product = self.create(clean)
        if clean.get('biotex_name'):
            product.name = product._biotex_build_name()
        if product.categ_id.biotex_level == 'family' and not product.default_code:
            product.action_assign_clave()
        return {
            'id': product.id, 'name': product.name, 'default_code': product.default_code,
            'state': product.biotex_class_state, 'missing': product.biotex_missing,
        }

    @api.model
    def biotex_classifier_queue(self, product_ids=None, limit=200):
        domain = [('id', 'in', product_ids)] if product_ids else [('biotex_class_state', '!=', 'complete')]
        products = self.search(domain, limit=limit, order='biotex_class_state, write_date')
        return products.read([
            'name', 'default_code', 'biotex_name', 'biotex_measure', 'biotex_content', 'biotex_family_id',
            'biotex_group_id', 'biotex_brand_id', 'biotex_model', 'biotex_manufacturer_id', 'biotex_reference',
            'biotex_usage_notes', 'biotex_equipment_ids', 'biotex_class_state', 'biotex_missing',
            'biotex_photo_count', 'image_128', 'description'])

    # ------------------------------------------------------------------ búsqueda por sinónimo / referencia
    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if value and operator in ('ilike', 'like', '=', '=ilike'):
            extra = Domain('biotex_synonym_ids.name', 'ilike', value) | Domain('biotex_reference', 'ilike', value) \
                | Domain('biotex_brand_id.name', 'ilike', value)
            domain = Domain(domain) | extra
        return domain
