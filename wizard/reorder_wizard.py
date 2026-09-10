from odoo import api, fields, models
from odoo.fields import Domain
from markupsafe import Markup
from odoo.exceptions import UserError
from odoo.addons.biotex_base.models.integrity import lock_records


class BiotexReorderWizard(models.TransientModel):
    """Reordena el consecutivo NN de una familia por medida numérica, dentro de cada combinación
    grupo-marca-familia-clasificador (proceso posterior, R04)."""
    _name = 'biotex.reorder.wizard'
    _description = 'Reordenar consecutivos por medida'

    family_id = fields.Many2one('product.category', domain=[('biotex_level', '=', 'family')])
    product_ids = fields.Many2many('product.template', string='Productos seleccionados')
    historical_prefix = fields.Char(string='Clasificación actual o anterior',help='Ejemplo: CE-LGMD-EDO-EKG. Incluye productos que antes tuvieron ese prefijo.')
    component = fields.Char(string='Ordenar por componente',help='Ejemplo: AGUJA o CABLE. Vacío utiliza la primera medida.')
    measure_type = fields.Char(string='Tipo de medida',help='Ejemplo: LARGO o CALIBRE.')
    preview = fields.Html(compute='_compute_preview')

    def _groups(self):
        domain=Domain('biotex_classifier_id','!=',False) & Domain('biotex_brand_id','!=',False)
        if self.product_ids:domain &= Domain('id','in',self.product_ids.ids)
        elif self.family_id:domain &= Domain('categ_id','=',self.family_id.id)
        elif not self.historical_prefix:return {}
        if self.historical_prefix:
            prefix=self.historical_prefix.strip().upper().rstrip('-')
            domain &= Domain('default_code','=like',prefix+'-%') | Domain('biotex_code_history_ids.prefix','=',prefix)
        products = self.env['product.template'].search(domain)
        buckets = {}
        for p in products:
            buckets.setdefault(p._biotex_clave_prefix(), self.env['product.template'])
            buckets[p._biotex_clave_prefix()] |= p
        return {k: v.sorted(key=self._sort_key) for k, v in buckets.items()}

    def _sort_key(self, product):
        measures=product.biotex_measure_ids.filtered(lambda r:
            (not self.component or r.component.casefold()==self.component.strip().casefold()) and
            (not self.measure_type or r.measure_type.casefold()==self.measure_type.strip().casefold()))
        if measures:
            measure=measures[0]
            factor={'MM':1,'CM':10,'M':1000}.get(measure.unit)
            return (0,measure.component,measure.measure_type,'MM' if factor else measure.unit,
                    measure.value * (factor or 1),product.name,product.id)
        return (1,'','','',product.biotex_measure_value,product.name,product.id)

    def _compute_preview(self):
        for wiz in self:
            rows = []
            for prefix, products in sorted(wiz._groups().items()):
                start = self.env['biotex.product.sequence']._next(prefix)
                for i, p in enumerate(products, start=start):
                    rows.append(Markup('<tr><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td></tr>') % (p.default_code or '-', p.name, p.biotex_measure_summary or p.biotex_measure or '', '%s%02d' % (prefix,i)))
            wiz.preview = Markup('<table class="table table-sm"><thead><tr><th>Clave actual</th><th>Producto</th><th>Medidas</th><th>Nueva clave</th></tr></thead><tbody>%s</tbody></table>') % Markup('').join(rows)

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group('biotex_base.group_biotex_direction'):
            raise UserError('Solo Dirección puede reordenar consecutivos.')
        if not self._groups():
            raise UserError('Seleccione productos, familia o una clasificación con productos para reordenar.')
        for prefix, products in sorted(self._groups().items()):
            lock_records(products)
            for p in products:
                i = self.env['biotex.product.sequence']._next(prefix, reserve=True)
                code = '%s%02d' % (prefix, i)
                vals = {'default_code': code, 'biotex_consecutive': i}
                if p.biotex_own_code:
                    vals['barcode'] = code
                p.write(vals)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
