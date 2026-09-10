from collections import defaultdict

from markupsafe import Markup
from odoo import api, fields, models, Command
from odoo.exceptions import UserError
from odoo.addons.biotex_base.models.integrity import lock_records


class ProductMergeWizard(models.TransientModel):
    _name='biotex.product.merge.wizard'
    _description='Unificar productos duplicados'

    product_ids=fields.Many2many('product.template',string='Registros a unificar',required=True)
    target_id=fields.Many2one('product.template',string='Producto que se conserva',required=True)
    preview=fields.Html(compute='_compute_preview')

    @api.depends('product_ids','target_id')
    def _compute_preview(self):
        for wizard in self:
            rows=[]
            for p in wizard.product_ids:
                rows.append(Markup('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') %
                    (p.default_code or '',p.name,p.uom_id.display_name,p.qty_available))
            wizard.preview=Markup('<table class="table table-sm"><thead><tr><th>Clave</th><th>Producto</th><th>Unidad</th><th>Existencias</th></tr></thead><tbody>%s</tbody></table>') % Markup('').join(rows)

    def action_merge(self):
        self.ensure_one()
        if not self.env.user.has_group('biotex_base.group_biotex_direction') and not self.env.su:
            raise UserError('Solo Dirección puede unificar productos.')
        products=self.product_ids.exists()
        target=self.target_id
        if len(products)<2 or target not in products:
            raise UserError('Seleccione al menos dos productos y conserve uno de ellos.')
        products.check_access('write')
        lock_records(products)
        variants=products.product_variant_ids
        lock_records(variants)
        if any(not p.active or p.type!='consu' or p.tracking!='none' or len(p.product_variant_ids)!=1 or p.company_id!=target.company_id or p.uom_id!=target.uom_id for p in products):
            raise UserError('Unifique productos activos sin variantes ni seguimiento por lote, con la misma empresa y unidad indivisible.')
        sources=products-target
        source_variants=sources.product_variant_ids
        # Only duplicate master data and available stock are consolidated. Operational
        # documents keep their product IDs and history; outstanding use must be resolved.
        if self.env['stock.move'].sudo().search_count([('product_id','in',variants.ids),('state','not in',['done','cancel'])],limit=1):
            raise UserError('Hay movimientos pendientes. Finalícelos antes de unificar los productos.')
        for model in ('sale.order.line','purchase.order.line','biotex.contract.line','biotex.purchase.request.line'):
            if model in self.env and 'product_id' in self.env[model]._fields:
                if self.env[model].sudo().search_count([('product_id','in',source_variants.ids)],limit=1):
                    raise UserError('Un registro a archivar tiene documentos relacionados (%s). Consérvelo como destino o concilie esos documentos primero.' % self.env[model]._description)
        if self.env['biotex.classification.session.line'].sudo().search_count([('product_id','in',products.ids),('session_id.state','=','draft')],limit=1):
            raise UserError('Quite estos productos de las sesiones pendientes antes de unificarlos.')
        quants=self.env['stock.quant'].sudo().search([('product_id','in',variants.ids),('location_id.usage','=','internal')])
        lock_records(quants)
        if any(q.reserved_quantity or q.quantity<0 or q.lot_id or q.owner_id or q.package_id for q in quants):
            raise UserError('Hay reservas, negativos, lotes, propietarios o paquetes que deben conciliarse antes de unificar.')
        companies=quants.company_id
        for company in companies:
            if company not in self.env.companies:
                raise UserError('Active todas las empresas con existencias de estos productos antes de unificar.')
            if any(p.with_company(company).standard_price!=target.with_company(company).standard_price for p in sources):
                raise UserError('Los costos de los registros difieren. Concilie el costo antes de unificar sus existencias.')
        before=defaultdict(float)
        for quant in quants:before[(quant.company_id.id,quant.location_id.id)]+=quant.quantity
        for source in sources:
            original_barcode=source.barcode
            packaging=source.product_variant_id.product_uom_ids
            if original_barcode:source.barcode=False
            packaging.write({'product_id':target.product_variant_id.id})
            target.uom_ids=[Command.link(uom.id) for uom in packaging.uom_id]
            if original_barcode:
                self.env['product.uom'].sudo().create({'product_id':target.product_variant_id.id,'uom_id':target.uom_id.id,
                    'barcode':original_barcode,'company_id':target.company_id.id})
            for code in set([source.default_code,source.biotex_legacy_code]+source.biotex_code_history_ids.mapped('code'))-{False,''}:
                self.env['biotex.product.code.history']._remember(target,code,'UNIFICACIÓN DE DUPLICADO')
            for quant in quants.filtered(lambda q:q.product_id==source.product_variant_id and q.quantity):
                Quant=self.env['stock.quant'].sudo().with_company(quant.company_id).with_context(inventory_mode=True,inventory_name='UNIFICACIÓN QA DE PRODUCTOS DUPLICADOS')
                destination=Quant.search([('product_id','=',target.product_variant_id.id),('location_id','=',quant.location_id.id),('lot_id','=',False),('owner_id','=',False),('package_id','=',False)])
                desired=sum(destination.mapped('quantity'))+quant.quantity
                quant.with_context(inventory_mode=True).inventory_quantity=0
                assert quant.with_context(inventory_mode=True).action_apply_inventory() is None
                dest=Quant.create({'product_id':target.product_variant_id.id,'location_id':quant.location_id.id,'inventory_quantity':desired})
                assert dest.action_apply_inventory() is None
            target.biotex_specialty_ids=[Command.link(i) for i in source.biotex_specialty_ids.ids]
            target.biotex_equipment_ids=[Command.link(i) for i in source.biotex_equipment_ids.ids]
            source.write({'active':False,'biotex_merged_into_id':target.id})
        after=defaultdict(float)
        for q in self.env['stock.quant'].sudo().search([('product_id','in',variants.ids),('location_id.usage','=','internal')]):
            after[(q.company_id.id,q.location_id.id)]+=q.quantity
        if dict(before)!=dict(after):raise UserError('La conciliación de existencias no coincide; se cancela la unificación.')
        target.message_post(body=Markup('<p>Productos unificados: %s. Se conservaron las cantidades por empresa y ubicación y los registros anteriores archivados.</p>') % ', '.join(sources.mapped('name')),subtype_xmlid='mail.mt_note')
        return {'type':'ir.actions.act_window','res_model':'product.template','res_id':target.id,'view_mode':'form','target':'current'}
