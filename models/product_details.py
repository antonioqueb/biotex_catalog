"""Structured physical measurements, native packaging barcodes and code history."""
import math
import unicodedata

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


def upper(value):
    return value.strip().upper() if isinstance(value, str) else value


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', upper(value or ''))
                           if not unicodedata.combining(c)).split())


def clean_measures(rows):
    if not isinstance(rows, list):
        raise ValidationError('Las medidas deben ser una lista.')
    result = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError('Medida no válida.')
        item = {k: upper(row.get(k) or '') for k in ('component', 'measure_type', 'unit')}
        try:
            item['value'] = float(row.get('value', 0))
        except (ValueError, TypeError):
            raise ValidationError('El valor de la medida debe ser numérico.')
        if not all(item.values()) or not math.isfinite(item['value']) or item['value'] <= 0:
            raise ValidationError('Complete componente, tipo, valor positivo y unidad en cada medida.')
        item['sequence'] = (i + 1) * 10
        result.append(item)
    return result


class ProductMeasure(models.Model):
    _name = 'biotex.product.measure'
    _description = 'Medida del producto'
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one('product.template', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='product_tmpl_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    component = fields.Char(string='Componente', required=True)
    measure_type = fields.Char(string='Tipo de medida', required=True)
    value = fields.Float(string='Valor', required=True, digits=(16, 6))
    unit = fields.Char(string='Unidad', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([{**v, **{k: upper(v[k]) for k in ('component','measure_type','unit') if k in v}} for v in vals_list])

    def write(self, vals):
        return super().write({**vals, **{k: upper(vals[k]) for k in ('component','measure_type','unit') if k in vals}})

    @api.constrains('component','measure_type','value','unit')
    def _check_measure(self):
        for row in self:
            clean_measures([{key: row[key] for key in ('component','measure_type','value','unit')}])

    def _measure_text(self):
        return '; '.join('%s %s %s %s' % (r.component, r.measure_type, '%g' % r.value, r.unit) for r in self)

    def _data(self):
        return [{key: r[key] for key in ('component','measure_type','value','unit')} for r in self]


class ProductCodeHistory(models.Model):
    _name = 'biotex.product.code.history'
    _description = 'Historial de claves del producto'
    _order = 'create_date desc, id desc'

    product_tmpl_id = fields.Many2one('product.template', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='product_tmpl_id.company_id', store=True)
    code = fields.Char(string='Clave anterior', required=True, index=True)
    prefix = fields.Char(string='Clasificación anterior', index=True)
    consecutive = fields.Integer(string='Consecutivo anterior')
    reason = fields.Char(string='Motivo', default='CAMBIO DE CLAVE')
    _code_product_unique = models.Constraint('unique(product_tmpl_id, code)', 'La clave ya está en el historial de este producto.')

    @api.model
    def _remember(self, product, code, reason='CAMBIO DE CLAVE'):
        if not code or self.sudo().search_count([('product_tmpl_id','=',product.id),('code','=',code)]):
            return
        parts = self.env['biotex.product.sequence']._split_code(code)
        self.sudo().create({'product_tmpl_id':product.id,'code':code,
            'prefix':parts[0] if parts else False,'consecutive':parts[1] if parts else 0,'reason':reason})


class ProductDetails(models.Model):
    _inherit = 'product.template'

    biotex_measure_ids = fields.One2many('biotex.product.measure', 'product_tmpl_id', string='Medidas por componente', copy=True)
    biotex_measure_summary = fields.Char(string='Medidas estructuradas', compute='_compute_measure_summary', store=True)
    biotex_description_extra = fields.Char(string='Complemento de descripción', help='Texto que se agrega a la descripción automática.')
    biotex_description_auto = fields.Char(string='Descripción automática', compute='_compute_description_auto')
    biotex_internal_notes = fields.Text(string='Notas internas')
    biotex_compatibility_notes = fields.Text(string='Compatibilidad')
    biotex_code_history_ids = fields.One2many('biotex.product.code.history','product_tmpl_id',string='Claves anteriores')
    biotex_merged_into_id = fields.Many2one('product.template',string='Unificado en',copy=False,readonly=True,ondelete='restrict')
    biotex_presentation_ids = fields.One2many('product.uom',compute='_compute_presentations',inverse='_inverse_presentations',readonly=False,string='Presentaciones y códigos de barras')
    biotex_optional_missing = fields.Char(string='Información opcional pendiente',compute='_compute_optional_missing')

    _UPPER_FIELDS = ('name','biotex_name','biotex_measure','biotex_content','biotex_model',
        'biotex_characteristics','biotex_usage_notes','biotex_description_extra','biotex_internal_notes','biotex_compatibility_notes')

    @api.depends('product_variant_ids.product_uom_ids')
    def _compute_presentations(self):
        for product in self:
            product.biotex_presentation_ids=product.product_variant_id.product_uom_ids if len(product.product_variant_ids)==1 else self.env['product.uom']

    def _inverse_presentations(self):
        for product in self:
            if len(product.product_variant_ids)!=1:
                raise UserError('Capture las presentaciones en un producto sin variantes.')
            product.product_variant_id.product_uom_ids=product.biotex_presentation_ids
            product.uom_ids=[Command.link(unit.id) for unit in product.biotex_presentation_ids.uom_id]

    @api.depends('biotex_measure_ids.component','biotex_measure_ids.measure_type','biotex_measure_ids.value','biotex_measure_ids.unit','biotex_measure_ids.sequence')
    def _compute_measure_summary(self):
        for product in self:
            product.biotex_measure_summary = product.biotex_measure_ids._measure_text()

    @api.depends('biotex_name','biotex_measure','biotex_measure_summary','biotex_description_extra')
    def _compute_description_auto(self):
        for product in self:
            product.biotex_description_auto = product._biotex_build_name()

    def _biotex_build_name(self):
        self.ensure_one()
        return ' '.join(upper(x) for x in (self.biotex_name, self.biotex_measure_summary or self.biotex_measure,
                                           self.biotex_description_extra) if x)

    @api.depends('biotex_reference','biotex_manufacturer_id','biotex_country_id','biotex_measure','biotex_measure_ids')
    def _compute_optional_missing(self):
        for p in self:
            p.biotex_optional_missing = ', '.join(label for label, present in [
                ('medidas', p.biotex_measure or p.biotex_measure_ids), ('referencia del fabricante',p.biotex_reference),
                ('fabricante',p.biotex_manufacturer_id),('país de origen',p.biotex_country_id)] if not present)

    @api.onchange('biotex_measure_ids','biotex_description_extra')
    def _onchange_detail_description(self):
        for product in self:
            if product.biotex_name:
                product.name = product._biotex_build_name()

    def action_use_structured_description(self):
        for product in self:
            if not product.biotex_name:
                raise UserError('Indique primero la descripción base.')
            product.name = product._biotex_build_name()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([{**v, **{k:upper(v[k]) for k in self._UPPER_FIELDS if k in v}} for v in vals_list])

    def write(self, vals):
        previous={p.id:(p.default_code,p.barcode) for p in self} if 'default_code' in vals else {}
        if 'uom_id' in vals:
            changing = self.filtered(lambda p: p.uom_id.id != vals['uom_id'])
            if changing and self.env['stock.move'].sudo().search_count([('product_id','in',changing.product_variant_ids.ids)],limit=1):
                raise UserError('La unidad indivisible tiene movimientos. Conserve esa unidad y registre las presentaciones con su equivalencia.')
        result=super().write({**vals, **{k:upper(vals[k]) for k in self._UPPER_FIELDS if k in vals}})
        for product in self:
            if product.id in previous and previous[product.id][0] and previous[product.id][0]!=product.default_code:
                old_code,old_barcode=previous[product.id]
                self.env['biotex.product.code.history']._remember(product,old_code)
                if old_barcode==old_code and product.barcode!=old_barcode:
                    product._biotex_keep_barcode(old_barcode)
        return result

    def _biotex_keep_barcode(self, barcode):
        self.ensure_one()
        Packaging=self.env['product.uom'].sudo()
        current=Packaging.search([('barcode','=',barcode)])
        if current:
            if current.product_id!=self.product_variant_id:
                raise ValidationError('El código anterior ya está asociado a otro producto.')
        else:
            Packaging.create({'product_id':self.product_variant_id.id,'uom_id':self.uom_id.id,'barcode':barcode,'company_id':self.company_id.id})

    def _biotex_presentation_data(self):
        """Empacados del producto para el asistente: tipo de empaque, cantidad de unidades indivisibles y código."""
        self.ensure_one()
        return [{'name': row.uom_id.name, 'quantity': row.uom_id._compute_quantity(1, self.uom_id, round=False),
                 'barcode': row.barcode, 'package_type_id': row._biotex_package_type().id or False}
                for row in self.product_variant_id.product_uom_ids]

    @api.model
    def _biotex_presentation_name(self, package_type, quantity):
        """Nombre de la unidad de empaque: "CAJA CON 12" (o solo "CAJA" cuando contiene una unidad)."""
        name = upper(package_type.name)
        return '%s CON %d' % (name, quantity) if quantity > 1 else name

    def _biotex_set_presentations(self, rows):
        self.ensure_one()
        self.check_access('write')
        if not isinstance(rows,list) or len(self.product_variant_ids) != 1:
            raise UserError('Use un producto sin variantes y una lista de presentaciones.')
        prepared, seen = [], set()
        PackageType = self.env['biotex.package.type']
        for row in rows:
            barcode = (row.get('barcode') or '').strip()
            try:
                quantity = float(row.get('quantity',0))
            except (TypeError,ValueError):
                raise ValidationError('La cantidad de presentación debe ser numérica.')
            # El asistente manda el tipo de empaque por renglón; el nombre de la unidad se compone de él.
            package_type = PackageType.browse(int(row['package_type_id'])).exists() if row.get('package_type_id') else PackageType
            name = upper(row.get('name') or '') if not package_type else self._biotex_presentation_name(package_type, int(quantity) if math.isfinite(quantity) else 0)
            if not name or not barcode or not math.isfinite(quantity) or quantity < 1 or quantity != int(quantity):
                raise ValidationError('Cada empacado requiere tipo de empaque, código y una cantidad entera de unidades indivisibles.')
            if barcode in seen:
                raise ValidationError('El código de barras está repetido en las presentaciones.')
            seen.add(barcode)
            # Only create a unit; never alter a conversion already used in operations.
            domain=[('name','=',name),('relative_uom_id','=',self.uom_id.id),('relative_factor','=',quantity)]
            unit=self.env['uom.uom'].search(domain,limit=1)
            if not unit:
                unit=self.env['uom.uom'].sudo().create({'name':name,'relative_uom_id':self.uom_id.id,'relative_factor':quantity})
            prepared.append((unit, barcode, package_type))
        current = self.product_variant_id.product_uom_ids
        historical=set(self.biotex_code_history_ids.mapped('code'))
        current.filtered(lambda r:r.barcode not in seen and r.barcode not in historical).unlink()
        for unit, barcode, package_type in prepared:
            row=current.filtered(lambda r:r.barcode==barcode)
            values = {'uom_id': unit.id, 'biotex_package_type_id': package_type.id or False}
            if row:
                row.write(values)
            else:
                self.env['product.uom'].create({'product_id':self.product_variant_id.id,'barcode':barcode,'company_id':self.company_id.id, **values})
            self.uom_ids = [Command.link(unit.id)]

    @api.model
    def _search_display_name(self, operator, value):
        domain=super()._search_display_name(operator,value)
        if value and operator in ('ilike','like','=','=ilike'):
            domain=Domain(domain) | Domain('biotex_code_history_ids.code',operator,value) | Domain('product_variant_ids.product_uom_ids.barcode',operator,value)
        return domain


class ProductVariantDetails(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        previous={p.id:(p.default_code,p.barcode) for p in self} if 'default_code' in vals else {}
        result=super().write(vals)
        for p in self:
            if p.id in previous and previous[p.id][0] and previous[p.id][0] != p.default_code:
                old_code,old_barcode=previous[p.id]
                self.env['biotex.product.code.history']._remember(p.product_tmpl_id,old_code)
                if old_barcode == old_code and p.barcode != old_barcode:
                    p.product_tmpl_id._biotex_keep_barcode(old_barcode)
        return result

    def _check_biotex_unique_code(self):
        super()._check_biotex_unique_code()
        for p in self:
            if p.default_code and self.env['biotex.product.code.history'].sudo().search_count([
                ('code','=',p.default_code),('product_tmpl_id','!=',p.product_tmpl_id.id)],limit=1):
                raise ValidationError('Esa clave pertenece al historial de otro producto y no puede reutilizarse.')

    @api.model
    def _search_display_name(self, operator, value):
        domain=super()._search_display_name(operator,value)
        if value and operator in ('ilike','like','=','=ilike'):
            domain=Domain(domain) | Domain('product_tmpl_id.biotex_code_history_ids.code',operator,value) | Domain('product_uom_ids.barcode',operator,value)
        return domain

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        result=super().name_search(name,domain,operator,limit)
        if name and operator in ('ilike','like','=','=ilike') and (not limit or len(result)<limit):
            extra=Domain('product_tmpl_id.biotex_code_history_ids.code',operator,name) | Domain('product_uom_ids.barcode',operator,name)
            found=self.search(Domain(domain or []) & extra & Domain('id','not in',[i for i,label in result]),limit=limit-len(result) if limit else None)
            result += [(r.id,r.display_name) for r in found]
        return result


class ProductPackagingBarcode(models.Model):
    _inherit='product.uom'

    biotex_quantity=fields.Float(string='Unidades indivisibles',compute='_compute_biotex_quantity')
    biotex_package_type_id = fields.Many2one('biotex.package.type', string='Tipo de empaque', ondelete='set null')

    def _biotex_package_type(self):
        """Tipo de empaque del renglón; para empacados antiguos se deduce del nombre de la unidad (CAJA CON 12 → CAJA)."""
        self.ensure_one()
        if self.biotex_package_type_id:
            return self.biotex_package_type_id
        first = upper(self.uom_id.name or '').split(' CON ')[0].strip()
        return self.env['biotex.package.type'].search([('name', '=ilike', first)], limit=1) if first else self.env['biotex.package.type']

    @api.depends('uom_id.factor','product_id.uom_id.factor')
    def _compute_biotex_quantity(self):
        for row in self:
            row.biotex_quantity=row.uom_id._compute_quantity(1,row.product_id.uom_id,round=False)

    @api.constrains('uom_id','product_id')
    def _check_biotex_quantity(self):
        for row in self:
            quantity=row.biotex_quantity
            if not row.uom_id._has_common_reference(row.product_id.uom_id) or quantity < 1 or quantity != int(quantity):
                raise ValidationError('La presentación debe contener unidades indivisibles completas del producto.')
