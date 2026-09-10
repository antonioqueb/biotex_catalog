from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['biotex.product.sequence']._observe_codes(records.mapped('default_code'))
        records._check_biotex_unique_code()
        return records

    def write(self, vals):
        if 'default_code' in vals:
            self.env['biotex.product.sequence']._observe_codes(self.mapped('default_code'))
        result = super().write(vals)
        if 'default_code' in vals:
            self.env['biotex.product.sequence']._observe_codes(self.mapped('default_code'))
            self._check_biotex_unique_code()
        return result

    def _check_biotex_unique_code(self):
        counter = self.env['biotex.product.sequence']
        for product in self:
            if counter._split_code(product.default_code) and self.sudo().with_context(active_test=False).search_count([
                ('default_code', '=', product.default_code), ('id', '!=', product.id),
            ], limit=1):
                raise ValidationError('La clave %s ya está utilizada por otro producto. Genere una clave nueva.' % product.default_code)

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if value and operator in ('ilike', 'like', '=', '=ilike'):
            extra = Domain('product_tmpl_id.biotex_synonym_ids.name', 'ilike', value) \
                | Domain('product_tmpl_id.biotex_reference', 'ilike', value) \
                | Domain('product_tmpl_id.biotex_brand_id.name', 'ilike', value)
            domain = Domain(domain) | extra
        return domain

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        res = super().name_search(name, domain, operator, limit)
        if name and operator in ('ilike', 'like', '=', '=ilike') and (not limit or len(res) < limit):
            extra = (Domain('product_tmpl_id.biotex_synonym_ids.name', 'ilike', name)
                     | Domain('product_tmpl_id.biotex_reference', 'ilike', name)
                     | Domain('product_tmpl_id.biotex_brand_id.name', 'ilike', name))
            found = [r[0] for r in res]
            records = self.search_fetch(Domain(domain or Domain.TRUE) & extra & Domain('id', 'not in', found),
                                        ['display_name'], limit=(limit - len(res)) if limit else None)
            res += [(r.id, r.display_name) for r in records]
        return res

    def action_print_qr_label(self):
        return self.env.ref('biotex_catalog.action_report_product_label_qr').report_action(self.product_tmpl_id)
