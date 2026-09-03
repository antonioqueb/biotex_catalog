from odoo import fields, models
from odoo.exceptions import UserError


class BiotexReorderWizard(models.TransientModel):
    """Reordena el consecutivo NN de una familia por medida numérica, dentro de cada combinación
    grupo-marca-familia-clasificador (proceso posterior, R04)."""
    _name = 'biotex.reorder.wizard'
    _description = 'Reordenar consecutivos por medida'

    family_id = fields.Many2one('product.category', required=True, domain=[('biotex_level', '=', 'family')])
    preview = fields.Html(compute='_compute_preview')

    def _groups(self):
        products = self.env['product.template'].search([('categ_id', '=', self.family_id.id), ('biotex_classifier_id', '!=', False), ('biotex_brand_id', '!=', False)])
        buckets = {}
        for p in products:
            buckets.setdefault(p._biotex_clave_prefix(), self.env['product.template'])
            buckets[p._biotex_clave_prefix()] |= p
        return {k: v.sorted(key=lambda p: (p.biotex_name or '', p.biotex_measure_value, p.biotex_measure or '', p.id)) for k, v in buckets.items()}

    def _compute_preview(self):
        for wiz in self:
            rows = []
            for prefix, products in sorted(wiz._groups().items()):
                for i, p in enumerate(products, start=1):
                    rows.append('<tr><td>%s</td><td>%s</td><td>%s</td><td><b>%s%02d</b></td></tr>' % (p.default_code or '-', p.name, p.biotex_measure or '', prefix, i))
            wiz.preview = ('<table class="table table-sm"><thead><tr><th>Clave actual</th><th>Producto</th><th>Medidas</th><th>Nueva clave</th></tr></thead><tbody>%s</tbody></table>' % ''.join(rows))

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group('biotex_base.group_biotex_direction'):
            raise UserError('Solo Dirección puede reordenar consecutivos.')
        for prefix, products in self._groups().items():
            for p in products:
                p.write({'default_code': 'TMP-%s' % p.id})
            for i, p in enumerate(products, start=1):
                code = '%s%02d' % (prefix, i)
                vals = {'default_code': code, 'biotex_consecutive': i}
                if p.biotex_own_code:
                    vals['barcode'] = code
                p.write(vals)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
