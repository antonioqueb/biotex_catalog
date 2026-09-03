from odoo import fields, models


class BiotexProductSynonym(models.Model):
    """Sinónimos y nombres coloquiales (ambú = resucitador) para búsqueda (R06)."""
    _name = 'biotex.product.synonym'
    _description = 'Sinónimo de producto'

    name = fields.Char(required=True, index=True)
    product_tmpl_id = fields.Many2one('product.template', required=True, ondelete='cascade', index=True)
    equivalent_tmpl_id = fields.Many2one(
        'product.template', string='Producto equivalente',
        help='Mismo producto con otra marca; se sugiere como sustituto.')
