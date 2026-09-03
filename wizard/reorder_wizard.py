from odoo import fields, models
from odoo.exceptions import UserError


class BiotexReorderWizard(models.TransientModel):
    """Reordena consecutivos de una familia por medida numérica (proceso posterior, R04)."""
    _name = 'biotex.reorder.wizard'
    _description = 'Reordenar consecutivos por medida'

    family_id = fields.Many2one('product.category', required=True, domain=[('biotex_level', '=', 'family')])
    preview = fields.Html(compute='_compute_preview')

    def _sorted_products(self):
        products = self.env['product.template'].search([('categ_id', '=', self.family_id.id)])
        return products.sorted(key=lambda p: (p.biotex_name or '', p.biotex_measure_value, p.biotex_measure or '', p.id))

    def _compute_preview(self):
        for wiz in self:
            rows = []
            for i, p in enumerate(wiz._sorted_products(), start=1):
                rows.append('<tr><td>%s</td><td>%s</td><td>%s</td><td><b>%04d</b></td></tr>' % (
                    p.default_code or '-', p.name, p.biotex_measure or '', i))
            wiz.preview = ('<table class="table table-sm"><thead><tr><th>Clave actual</th><th>Producto</th>'
                           '<th>Medida</th><th>Nuevo consecutivo</th></tr></thead><tbody>%s</tbody></table>' % ''.join(rows))

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group('biotex_base.group_biotex_direction'):
            raise UserError('Solo Dirección puede reordenar consecutivos.')
        products = self._sorted_products()
        prefix = self.family_id.biotex_sequence_id.prefix or '%s-%s-' % (
            self.family_id.parent_id.biotex_code, self.family_id.biotex_code)
        # dos pasadas para evitar colisiones temporales
        for p in products:
            p.write({'default_code': 'TMP-%s' % p.id})
        for i, p in enumerate(products, start=1):
            code = '%s%04d' % (prefix, i)
            vals = {'default_code': code, 'biotex_consecutive': i}
            if p.biotex_own_code:
                vals['barcode'] = code
            p.write(vals)
        if self.family_id.biotex_sequence_id:
            self.family_id.biotex_sequence_id.sudo().number_next_actual = len(products) + 1
        return {'type': 'ir.actions.client', 'tag': 'reload'}
