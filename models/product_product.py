from odoo import api, models
from odoo.fields import Domain


class ProductProduct(models.Model):
    _inherit = 'product.product'

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
