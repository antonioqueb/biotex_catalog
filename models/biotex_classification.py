"""Asistente de clasificación masiva: una clasificación y N productos.

A diferencia del asistente guiado (`biotex_catalog.classifier`, producto por producto), aquí se
fija primero la clasificación —grupo, familia, clasificador y marca— y después se van agregando
productos a esa misma clasificación. La sesión es un registro persistente para poder "Guardar y
salir" y retomarla más tarde.

Reglas de la iteración 1:

* El consecutivo se **reserva al agregar** el producto y ya no cambia al reordenar la lista: el
  orden es prioridad de trabajo, la numeración es identidad. Solo se reasigna si cambia la
  clasificación de la sesión (cambia el prefijo, luego la referencia entera deja de valer).
* La referencia solo se escribe en `default_code` **al confirmar** la sesión. Mientras esté en
  borrador es una vista previa: nada se reserva en el catálogo.
* El formato de clave es el del esquema v2 vigente, `GG-MMMM-FFF-CCC-NN`
  (grupo · marca · familia · clasificador · consecutivo), el mismo que produce
  `product.template.action_assign_clave`.
"""
import hashlib
import json

from markupsafe import Markup
from odoo import api, fields, models
from odoo.tools import SQL
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

CONSECUTIVE_FORMAT = '%02d'


class BiotexClassificationSession(models.Model):
    _name = 'biotex.classification.session'
    _description = 'Sesión de clasificación de productos'
    _order = 'create_date desc'

    name = fields.Char(compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', string='Responsable', required=True, default=lambda self: self.env.user, index=True)
    date = fields.Datetime(string='Fecha', required=True, default=fields.Datetime.now)
    state = fields.Selection([
        ('draft', 'Borrador'), ('confirmed', 'Confirmada'), ('cancelled', 'Cancelada')],
        default='draft', required=True, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)

    group_id = fields.Many2one('biotex.group', string='Grupo', ondelete='restrict')
    family_id = fields.Many2one(
        'product.category', string='Familia', ondelete='restrict',
        domain="[('biotex_level', '=', 'family'), ('biotex_group_id', '=', group_id)]")
    classifier_id = fields.Many2one(
        'biotex.classifier', string='Clasificador', ondelete='restrict',
        domain="[('id', 'in', allowed_classifier_ids)]")
    allowed_classifier_ids = fields.Many2many('biotex.classifier', compute='_compute_allowed_classifier_ids')
    brand_id = fields.Many2one('biotex.brand', string='Marca', ondelete='restrict')

    class_code = fields.Char(string='Clave de clasificación', compute='_compute_class_code', store=True, index=True)
    complete = fields.Boolean(string='Clasificación completa', compute='_compute_class_code', store=True)
    line_ids = fields.One2many('biotex.classification.session.line', 'session_id', string='Productos')
    line_count = fields.Integer(compute='_compute_line_count')

    # ------------------------------------------------------------------ computes
    @api.depends('group_id.code', 'brand_id.code', 'family_id.biotex_code', 'classifier_id.code')
    def _compute_class_code(self):
        for session in self:
            parts = (session.group_id.code, session.brand_id.code, session.family_id.biotex_code, session.classifier_id.code)
            session.complete = all(parts)
            session.class_code = '-'.join(parts) if session.complete else False

    @api.depends('class_code', 'date')
    def _compute_name(self):
        for session in self:
            session.name = '%s · %s' % (session.class_code or 'Sin clasificación', fields.Date.to_string(session.date or fields.Datetime.now()))

    @api.depends('family_id.biotex_classifier_ids')
    def _compute_allowed_classifier_ids(self):
        for session in self:
            session.allowed_classifier_ids = session.family_id.biotex_classifier_ids

    @api.depends('line_ids')
    def _compute_line_count(self):
        data = self.env['biotex.classification.session.line']._read_group([('session_id', 'in', self.ids)], ['session_id'], ['__count'])
        counts = {session.id: count for session, count in data}
        for session in self:
            session.line_count = counts.get(session.id, 0)

    # ------------------------------------------------------------------ constraints
    @api.constrains('group_id', 'family_id', 'classifier_id')
    def _check_hierarchy(self):
        for session in self:
            if session.family_id and session.group_id and session.family_id.biotex_group_id != session.group_id:
                raise ValidationError('La familia %s no pertenece al grupo %s.' % (session.family_id.biotex_code, session.group_id.code))
            if session.classifier_id and session.family_id and session.classifier_id not in session.family_id.biotex_classifier_ids:
                raise ValidationError('El clasificador %s no está autorizado para la familia %s.' % (
                    session.classifier_id.code, session.family_id.biotex_composite))

    # ------------------------------------------------------------------ consecutivos
    def _lock_workspace(self):
        if not self:
            return
        self.check_access('write')
        self.env.cr.execute(SQL('SELECT id FROM biotex_classification_session WHERE id IN %s ORDER BY id FOR UPDATE', tuple(self.ids)))
        # Touch the row so concurrent RPCs retry under Odoo's repeatable-read isolation,
        # including when only child rows change (add/remove/edit).
        self.env.cr.execute(SQL('UPDATE biotex_classification_session SET write_date = write_date WHERE id IN %s', tuple(self.ids)))
        self.invalidate_recordset()

    def _next_consecutive(self):
        """Primer consecutivo libre del prefijo: mira las claves ya escritas y las reservadas por otras sesiones."""
        self.ensure_one()
        if not self.class_code:
            raise UserError('Defina la clasificación completa antes de reservar consecutivos.')
        product = self.env['product.template'].search(
            [('default_code', '=like', self.class_code + '-%')], order='biotex_consecutive desc', limit=1)
        line = self.env['biotex.classification.session.line'].search(
            [('session_id.class_code', '=', self.class_code), ('session_id.state', '!=', 'cancelled')],
            order='consecutive desc', limit=1)
        return max(product.biotex_consecutive or 0, line.consecutive or 0) + 1

    def _reassign_consecutives(self):
        """Renumera la sesión completa: solo tras cambiar la clasificación, porque cambia el prefijo."""
        self.ensure_one()
        lines = self.line_ids.sorted(lambda l: (l.sequence, l.id))
        lines.consecutive = 0
        for line in lines:
            line.consecutive = self._next_consecutive()

    # ------------------------------------------------------------------ acciones
    def action_open_workspace(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'biotex_catalog.classification_workspace',
            'name': 'Asistente de clasificación',
            'context': {'biotex_session_id': self.id},
        }

    def action_confirm(self, expected_revision=None):
        """Escribe la clasificación, el nombre, la unidad y la referencia definitiva en cada producto."""
        for session in self:
            session._lock_workspace()
            if session.state != 'draft':
                raise UserError('La sesión %s ya no está en borrador.' % session.name)
            if not session.complete:
                raise UserError('Complete la clasificación (grupo, familia, clasificador y marca) antes de generar las claves.')
            if not session.line_ids:
                raise UserError('Agregue al menos un producto antes de generar las claves.')
            products = session.line_ids.product_id
            products.check_access('write')
            self.env.cr.execute(SQL('SELECT id FROM product_template WHERE id IN %s ORDER BY id FOR UPDATE', tuple(products.ids)))
            self.env.cr.execute(SQL('SELECT id FROM product_product WHERE product_tmpl_id IN %s ORDER BY id FOR UPDATE', tuple(products.ids)))
            products.invalidate_recordset()
            products.product_variant_ids.invalidate_recordset()
            preview = session.workspace_confirmation_preview()
            if expected_revision and expected_revision != preview['revision']:
                raise UserError('La sesión o un producto cambió desde la revisión. Abra de nuevo Generar claves y revise las referencias actuales.')
            if preview['changes'] and not expected_revision:
                raise UserError('Hay referencias existentes que cambiarán. Abra el asistente y revise la clasificación anterior y nueva antes de confirmar.')
            for line in session.line_ids:
                line._apply()
            super(BiotexClassificationSession, session).write({'state': 'confirmed'})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('state', 'draft') != 'draft' for vals in vals_list):
            raise UserError('Cree la sesión en borrador y confirme desde el asistente.')
        return super().create(vals_list)

    def write(self, vals):
        self._lock_workspace()
        if any(session.state == 'confirmed' for session in self):
            raise UserError('La sesión confirmada conserva su historial. Cree una nueva sesión para reclasificar.')
        if vals.get('state') == 'confirmed':
            raise UserError('Use Generar claves para confirmar la sesión.')
        return super().write(vals)

    def unlink(self):
        self._lock_workspace()
        if any(session.state == 'confirmed' for session in self):
            raise UserError('No se elimina una clasificación confirmada.')
        return super().unlink()

    def action_cancel(self):
        for session in self:
            if session.state == 'confirmed':
                raise UserError('No se puede cancelar una sesión ya confirmada.')
            session.state = 'cancelled'
        return True

    def action_draft(self):
        self.filtered(lambda s: s.state == 'cancelled').state = 'draft'
        return True

    def action_view_products(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Productos de %s' % self.name, 'res_model': 'product.template',
                'view_mode': 'list,form', 'domain': [('id', 'in', self.line_ids.product_id.ids)]}

    # ================================================================== API del asistente OWL
    @api.model
    def workspace_bootstrap(self, session_id=None):
        """Todo lo que la pantalla necesita en una sola llamada: árbol, marcas, unidades y sesión."""
        session = self.browse(session_id).exists() if session_id else self.browse()
        return {
            'tree': self.env['product.category'].biotex_get_tree(),
            'brands': self.env['biotex.brand'].search_read([], ['id', 'name', 'code'], order='name'),
            'uoms': self.env['uom.uom'].search_read([], ['id', 'name'], order='sequence, id'),
            'session': session._workspace_session() if session else None,
            'drafts': [{
                'id': draft.id, 'class_code': draft.class_code or '', 'line_count': draft.line_count,
            } for draft in self.search([('state', '=', 'draft'), ('user_id', '=', self.env.uid), ('id', '!=', session.id)], limit=5)],
        }

    def _workspace_session(self):
        self.ensure_one()
        return {
            'id': self.id,
            'state': self.state,
            'class_code': self.class_code or '',
            'complete': self.complete,
            'group_id': self.group_id.id or False,
            'family_id': self.family_id.id or False,
            'classifier_id': self.classifier_id.id or False,
            'brand_id': self.brand_id.id or False,
            'lines': [line._workspace_line() for line in self.line_ids.sorted(lambda l: (l.sequence, l.id))],
        }

    @api.model
    def workspace_set_classification(self, session_id, vals):
        """Crea la sesión en cuanto la clasificación está completa, o la actualiza renumerando si cambia el prefijo."""
        clean = {k: vals.get(k) or False for k in ('group_id', 'family_id', 'classifier_id', 'brand_id')}
        session = self.browse(session_id).exists() if session_id else self.browse()
        if not session:
            if not all(clean.values()):
                return None  # todavía no hay nada que persistir
            session = self.create(clean)
        else:
            session._lock_workspace()
            session._check_editable()
            previous = session.class_code
            session.write(clean)
            if session.class_code != previous and session.line_ids:
                # cambió el prefijo: la referencia entera deja de valer y hay que renumerar
                if session.class_code:
                    session._reassign_consecutives()
                else:
                    session.line_ids.consecutive = 0
        return session._workspace_session()

    def workspace_search_products(self, query='', offset=0, limit=20):
        """Búsqueda paginada por nombre, clave, referencia de fabricante, código de barras o sinónimo."""
        self.ensure_one()
        self.check_access('read')
        limit = max(1, min(int(limit), 20))
        offset = max(0, int(offset))
        domain = Domain('id', 'not in', self.line_ids.product_id.ids)
        query = (query or '').strip()
        if query:
            domain &= (Domain('name', 'ilike', query) | Domain('default_code', 'ilike', query)
                       | Domain('biotex_reference', 'ilike', query) | Domain('barcode', 'ilike', query)
                       | Domain('biotex_alt_code', 'ilike', query) | Domain('biotex_legacy_code', 'ilike', query)
                       | Domain('biotex_synonym_ids.name', 'ilike', query))
        Product = self.env['product.template']
        total = Product.search_count(domain)
        # Removing the last row of the last page must not leave an empty, inaccessible page.
        offset = min(offset, ((total - 1) // limit) * limit) if total else 0
        products = Product.search(domain, offset=offset, limit=limit, order='name, id')
        return {
            'total': total,
            'offset': offset,
            'limit': limit,
            'records': [{
                'id': p.id,
                'name': p.name,
                'default_code': p.default_code or '',
                'reference': p.biotex_reference or p.barcode or '',
                'brand': p.biotex_brand_id.name or '',
            } for p in products],
        }

    def workspace_add_products(self, product_ids):
        self.ensure_one()
        self._lock_workspace()
        self._check_editable()
        existing = set(self.line_ids.product_id.ids)
        sequence = max(self.line_ids.mapped('sequence') or [0])
        Line = self.env['biotex.classification.session.line']
        products = self.env['product.template'].browse(list(dict.fromkeys(pid for pid in product_ids if pid not in existing))).exists()
        products.check_access('read')
        for product in products:
            sequence += 10
            Line.create({
                'session_id': self.id,
                'product_id': product.id,
                'sequence': sequence,
                'consecutive': self._next_consecutive(),
                'old_name': product.name,
                'old_reference': product.default_code or '',
                'new_name': product.name,
                'uom_id': product.uom_id.id,
                'measure': product.biotex_measure,
                'content': product.biotex_content,
                'package_type_id': product.biotex_package_type_id.id,
                'package_qty': product.biotex_package_qty or 1.0,
                'brand_id': product.biotex_brand_id.id,
                'manufacturer_ref': product.biotex_reference,
                'model': product.biotex_model,
                'barcode': product.barcode,
                'country_id': product.biotex_country_id.id,
                'manufacturer_id': product.biotex_manufacturer_id.id,
                'distributor_id': product.biotex_primary_distributor_id.id,
                'equipment_id': product.biotex_main_equipment_id.id,
                'specialty_id': product.biotex_main_specialty_id.id,
                'notes': product.biotex_characteristics,
            })
        return self._workspace_session()

    def workspace_remove_line(self, line_id):
        self.ensure_one()
        self._check_editable()
        (self.line_ids & self.env['biotex.classification.session.line'].browse(line_id)).unlink()
        return self._workspace_session()

    def workspace_reorder(self, line_ids):
        """Persiste el orden de trabajo. No toca los consecutivos: son dos conceptos distintos."""
        self.ensure_one()
        self._check_editable()
        lines = self.line_ids
        for position, line_id in enumerate(line_ids, start=1):
            line = lines.filtered(lambda l: l.id == line_id)
            if line:
                line.sequence = position * 10
        return self._workspace_session()

    def workspace_update_line(self, line_id, vals):
        """Guarda el detalle de una línea. Valida en servidor lo que el modal valida en pantalla."""
        self.ensure_one()
        self._check_editable()
        Line = self.env['biotex.classification.session.line']
        line = self.line_ids.filtered(lambda l: l.id == line_id)
        if not line:
            raise UserError('La línea ya no pertenece a esta sesión.')
        allowed = ('new_name', 'uom_id') + Line.DETAIL_FIELDS
        clean = {k: v for k, v in vals.items() if k in allowed}
        def effective(field, current):
            # un campo enviado vacío es un borrado deliberado; uno ausente conserva lo guardado
            return clean[field] if field in clean else current
        if not (effective('new_name', line.new_name) or '').strip():
            raise UserError('El nuevo nombre es obligatorio.')
        if not effective('uom_id', line.uom_id.id):
            raise UserError('La unidad de medida es obligatoria.')
        qty = effective('package_qty', line.package_qty)
        if qty is not None and qty != '' and float(qty) <= 0:
            raise UserError('La cantidad de presentación debe ser un número positivo.')
        barcode = (clean.get('barcode') or '').strip()
        if barcode:
            clash = self.env['product.template'].search(
                [('barcode', '=', barcode), ('id', '!=', line.product_id.id)], limit=1)
            if clash:
                raise UserError('El código de barras %s ya pertenece a "%s".' % (barcode, clash.display_name))
            other = Line.search([('barcode', '=', barcode), ('id', '!=', line.id),
                                 ('session_id.state', '=', 'draft')], limit=1)
            if other:
                raise UserError('El código de barras %s ya está capturado en la línea "%s" de esta clasificación.' % (barcode, other.display_name))
            clean['barcode'] = barcode
        ref = (clean.get('manufacturer_ref') or '').strip()
        if ref:
            clash = self.env['product.template'].search(
                [('biotex_reference', '=ilike', ref), ('id', '!=', line.product_id.id)], limit=1)
            if clash:
                raise UserError('La referencia del fabricante %s ya pertenece a "%s". No se repite entre productos.' % (ref, clash.display_name))
            clean['manufacturer_ref'] = ref
        line.write(clean)
        return self._workspace_session()

    def workspace_line_detail(self, line_id):
        """Datos de la línea y catálogos que el modal necesita, en una sola llamada."""
        self.ensure_one()
        line = self.line_ids.filtered(lambda l: l.id == line_id)
        if not line:
            raise UserError('La línea ya no pertenece a esta sesión.')
        return {
            'line': line._workspace_detail(),
            'catalogs': {
                'uoms': self.env['uom.uom'].search_read([], ['id', 'name'], order='sequence, id'),
                'package_types': self.env['biotex.package.type'].search_read([], ['id', 'name'], order='sequence, name'),
                'countries': self.env['res.country'].search_read([], ['id', 'name'], order='name'),
                'brands': self.env['biotex.brand'].search_read([], ['id', 'name', 'code'], order='name'),
                'specialties': self.env['biotex.specialty'].search_read([], ['id', 'name', 'code'], order='name'),
                'contents': sorted({p['biotex_content'] for p in self.env['product.template'].search_read(
                    [('biotex_content', '!=', False)], ['biotex_content'], limit=500) if p['biotex_content']}),
            },
            'classification_brand_id': self.brand_id.id or False,
            'classification_brand_name': self.brand_id.display_name or '',
        }

    @api.model
    def workspace_search_relation(self, model, query, limit=10):
        """Buscador para fabricante, distribuidor y equipo: usa los catálogos existentes, no crea nada."""
        allowed = {
            'res.partner': [('is_company', '=', True)],
            'biotex.equipment': [],
        }
        if model not in allowed:
            raise UserError('Modelo no permitido en el buscador del asistente.')
        domain = list(allowed[model])
        if model == 'res.partner' and (self.env.context.get('biotex_supplier_only')):
            domain.append(('supplier_rank', '>', 0))
        records = self.env[model].search(domain + [('display_name', 'ilike', query or '')], limit=limit)
        return [{'id': r.id, 'name': r.display_name} for r in records]

    @api.model
    def workspace_brand_hints(self, family_id, classifier_id):
        """Marcas ya usadas con esta familia y clasificador: se ofrecen primero al elegir marca."""
        if not (family_id and classifier_id):
            return []
        return self.env['product.template'].search(
            [('categ_id', '=', family_id), ('biotex_classifier_id', '=', classifier_id)]
        ).biotex_brand_id.ids

    def workspace_confirmation_preview(self):
        """Current values, rather than the potentially stale values captured when adding a product."""
        self.ensure_one()
        self.check_access('read')
        self._check_editable()
        changes = []
        version = [self.class_code, self.company_id.id]
        for line in self.line_ids.sorted('id'):
            product = line.product_id
            previous = product.default_code or ''
            if previous and previous != line.reference:
                changes.append({'id': product.id, 'name': product.name, 'before': previous, 'after': line.reference})
            version.append([line._workspace_detail(), previous, str(product.write_date),
                            product.name, product.uom_id.id, line._classification_description(product)])
        return {'revision': hashlib.sha256(json.dumps(version).encode()).hexdigest(),
                'count': len(self.line_ids), 'changes': changes}

    def workspace_confirm(self, expected_revision=None):
        self.ensure_one()
        self.action_confirm(expected_revision=expected_revision)
        return self._workspace_session()

    def workspace_discard(self):
        """"Cancelar": una sesión vacía se borra, una con trabajo se marca cancelada para dejar rastro."""
        self.ensure_one()
        if self.state == 'draft' and not self.line_ids:
            self.unlink()
            return True
        self.action_cancel()
        return True

    def _check_editable(self):
        if self.state != 'draft':
            raise UserError('La sesión %s ya no es editable.' % self.name)


class BiotexClassificationSessionLine(models.Model):
    _name = 'biotex.classification.session.line'
    _description = 'Producto de una sesión de clasificación'
    _order = 'sequence, id'

    session_id = fields.Many2one('biotex.classification.session', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Orden', default=10, index=True)
    product_id = fields.Many2one('product.template', string='Producto', required=True, ondelete='cascade', index=True)
    old_name = fields.Char(string='Nombre anterior', readonly=True, help='Nombre que tenía el producto al agregarlo a la sesión.')
    old_reference = fields.Char(string='Referencia al agregar', readonly=True)
    applied_reference_before = fields.Char(string='Referencia anterior', readonly=True, copy=False)
    applied_reference_after = fields.Char(string='Referencia aplicada', readonly=True, copy=False)
    applied_classification_before = fields.Char(string='Clasificación anterior', readonly=True, copy=False)
    applied_classification_after = fields.Char(string='Clasificación aplicada', readonly=True, copy=False)
    applied_by_id = fields.Many2one('res.users', string='Aplicó', readonly=True, copy=False, ondelete='restrict')
    applied_on = fields.Datetime(string='Fecha de aplicación', readonly=True, copy=False)
    new_name = fields.Char(string='Nombre actual')
    uom_id = fields.Many2one('uom.uom', string='Unidad de medida')
    consecutive = fields.Integer(string='Consecutivo', readonly=True, copy=False,
                                help='Se reserva al agregar el producto y no cambia al reordenar la lista.')
    reference = fields.Char(string='Referencia generada', compute='_compute_reference', store=True)
    state = fields.Selection([('draft', 'Pendiente'), ('applied', 'Aplicada')], default='draft', required=True)

    # --- información adicional: se captura en la sesión y se escribe en el producto al confirmar ---
    measure = fields.Char(string='Medidas')
    content = fields.Char(string='UI unidad indivisible')
    package_type_id = fields.Many2one('biotex.package.type', string='Tipo de empaque', ondelete='restrict')
    package_qty = fields.Float(string='Cantidad de presentación', default=1.0)
    brand_id = fields.Many2one('biotex.brand', string='Marca del producto', ondelete='restrict',
                               help='Marca almacenada como atributo. La marca de la clasificación se define en la sesión.')
    manufacturer_ref = fields.Char(string='Referencia del fabricante')
    model = fields.Char(string='Modelo')
    barcode = fields.Char(string='Código de barras')
    country_id = fields.Many2one('res.country', string='País de origen')
    manufacturer_id = fields.Many2one('res.partner', string='Fabricante')
    distributor_id = fields.Many2one('res.partner', string='Distribuidor primario')
    equipment_id = fields.Many2one('biotex.equipment', string='Equipo relacionado')
    specialty_id = fields.Many2one('biotex.specialty', string='Especialidad')
    notes = fields.Text(string='Notas')

    DETAIL_FIELDS = ('measure', 'content', 'package_type_id', 'package_qty', 'brand_id', 'manufacturer_ref', 'model',
                     'barcode', 'country_id', 'manufacturer_id', 'distributor_id', 'equipment_id', 'specialty_id', 'notes')
    AUDIT_FIELDS = ('applied_reference_before', 'applied_reference_after', 'applied_classification_before',
                   'applied_classification_after', 'applied_by_id', 'applied_on')

    @api.model_create_multi
    def create(self, vals_list):
        sessions = self.env['biotex.classification.session'].browse(list({v['session_id'] for v in vals_list}))
        sessions._lock_workspace()
        for session in sessions:
            session._check_editable()
        if any(set(vals) & set(self.AUDIT_FIELDS) or vals.get('state', 'draft') != 'draft' for vals in vals_list):
            raise UserError('El historial de aplicación se registra al confirmar.')
        return super().create(vals_list)

    def write(self, vals):
        self.session_id._lock_workspace()
        if any(line.state == 'applied' or line.session_id.state != 'draft' for line in self):
            raise UserError('Conserve la línea aplicada en su sesión original.')
        if set(vals) & (set(self.AUDIT_FIELDS) | {'state', 'session_id', 'product_id', 'old_reference', 'old_name'}):
            raise UserError('La identidad y el historial de la línea no se modifican manualmente.')
        return super().write(vals)

    def unlink(self):
        self.session_id._lock_workspace()
        if any(line.state == 'applied' or line.session_id.state == 'confirmed' for line in self):
            raise UserError('No se elimina una línea de clasificación aplicada.')
        return super().unlink()

    @api.constrains('package_qty')
    def _check_package_qty(self):
        for line in self:
            if line.package_qty and line.package_qty <= 0:
                raise ValidationError('La cantidad de presentación debe ser un número positivo.')

    _product_uniq = models.Constraint(
        'unique(session_id, product_id)',
        'El producto ya está en esta sesión de clasificación.',
    )

    @api.depends('session_id.class_code', 'consecutive')
    def _compute_reference(self):
        for line in self:
            code = line.session_id.class_code
            line.reference = ('%s-' + CONSECUTIVE_FORMAT) % (code, line.consecutive) if code and line.consecutive else False

    @api.depends('product_id.name', 'new_name')
    def _compute_display_name(self):
        for line in self:
            line.display_name = line.new_name or line.product_id.name

    def _workspace_line(self):
        self.ensure_one()
        return {
            'id': self.id,
            'product_id': self.product_id.id,
            'sequence': self.sequence,
            'old_name': self.old_name or '',
            'old_reference': self.old_reference or '',
            'new_name': self.new_name or '',
            'uom_id': self.uom_id.id or False,
            'uom_name': self.uom_id.name or '',
            'consecutive': self.consecutive,
            'consecutive_label': CONSECUTIVE_FORMAT % self.consecutive if self.consecutive else '',
            'reference': self.reference or '',
            'state': self.state,
            'brand_name': self.brand_id.display_name or '',
            'measure': self.measure or '',
            'barcode': self.barcode or '',
            'detail_filled': sum(1 for f in self.DETAIL_FIELDS if self[f]),
        }

    def _workspace_detail(self):
        """Todos los campos editables del modal, con etiquetas de los relacionados."""
        self.ensure_one()
        data = self._workspace_line()
        data.update({
            'measure': self.measure or '',
            'content': self.content or '',
            'package_type_id': self.package_type_id.id or False,
            'package_qty': self.package_qty or 1.0,
            'brand_id': self.brand_id.id or False,
            'manufacturer_ref': self.manufacturer_ref or '',
            'model': self.model or '',
            'barcode': self.barcode or '',
            'country_id': self.country_id.id or False,
            'manufacturer_id': self.manufacturer_id.id or False,
            'manufacturer_name': self.manufacturer_id.display_name or '',
            'distributor_id': self.distributor_id.id or False,
            'distributor_name': self.distributor_id.display_name or '',
            'equipment_id': self.equipment_id.id or False,
            'equipment_name': self.equipment_id.display_name or '',
            'specialty_id': self.specialty_id.id or False,
            'notes': self.notes or '',
        })
        return data

    def _apply(self):
        """Escribe la clasificación y la referencia en el producto. Solo se llama al confirmar."""
        self.ensure_one()
        session = self.session_id
        product = self.product_id
        previous_reference = product.default_code or ''
        previous_classification = self._classification_description(product)
        vals = {
            'categ_id': session.family_id.id,
            'biotex_classifier_id': session.classifier_id.id,
            'biotex_brand_id': session.brand_id.id,
            'default_code': self.reference,
            'biotex_consecutive': self.consecutive,
        }
        if self.new_name and self.new_name != product.name:
            vals['name'] = self.new_name
        if self.uom_id and self.uom_id != product.uom_id:
            vals['uom_id'] = self.uom_id.id
        detail = {
            'biotex_measure': self.measure, 'biotex_content': self.content,
            'biotex_package_type_id': self.package_type_id.id, 'biotex_package_qty': self.package_qty or 1.0,
            'biotex_brand_id': self.brand_id.id or session.brand_id.id,
            'biotex_reference': self.manufacturer_ref, 'biotex_model': self.model,
            'biotex_country_id': self.country_id.id, 'biotex_manufacturer_id': self.manufacturer_id.id,
            'biotex_primary_distributor_id': self.distributor_id.id, 'biotex_characteristics': self.notes,
        }
        vals.update({k: v for k, v in detail.items() if v})
        if self.barcode:
            vals['barcode'] = self.barcode
        elif not product.barcode and not product.biotex_reference and not self.manufacturer_ref:
            vals['barcode'] = self.reference
        if self.equipment_id:
            vals['biotex_main_equipment_id'] = self.equipment_id.id
            vals['biotex_equipment_ids'] = [(4, self.equipment_id.id)]
        if self.specialty_id:
            vals['biotex_main_specialty_id'] = self.specialty_id.id
            vals['biotex_specialty_ids'] = [(4, self.specialty_id.id)]
        product.write(vals)
        applied_on = fields.Datetime.now()
        current_classification = self._classification_description(product)
        super(BiotexClassificationSessionLine, self).write({
            'state': 'applied', 'applied_reference_before': previous_reference,
            'applied_reference_after': product.default_code or '',
            'applied_classification_before': previous_classification,
            'applied_classification_after': current_classification,
            'applied_by_id': self.env.uid, 'applied_on': applied_on,
        })
        product.message_post(body=Markup(
            '<p>Clasificación aplicada desde la sesión %s.</p>'
            '<p>Referencia: %s → %s</p><p>Clasificación: %s → %s</p>'
            '<p>Responsable: %s · Fecha (UTC): %s</p>'
        ) % (session.name, previous_reference or 'Sin referencia', product.default_code or '',
             previous_classification, current_classification, self.env.user.display_name, applied_on),
            subtype_xmlid='mail.mt_note')

    def _classification_description(self, product):
        return ' / '.join(value or 'Sin asignar' for value in (
            product.biotex_group_id.display_name, product.biotex_brand_id.display_name,
            product.categ_id.display_name, product.biotex_classifier_id.display_name))
