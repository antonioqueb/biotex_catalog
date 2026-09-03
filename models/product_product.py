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

    def action_print_qr_label(self):
        return self.env.ref('biotex_catalog.action_report_product_label_qr').report_action(self.product_tmpl_id)
