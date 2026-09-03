from odoo import api, fields, models


class BiotexEquipment(models.Model):
    """Equipo (marca + modelo) con el que un insumo es compatible: cables, sensores, circuitos."""
    _name = 'biotex.equipment'
    _description = 'Equipo compatible'
    _order = 'brand_id, model'
    _rec_name = 'display_name'

    brand_id = fields.Many2one('biotex.brand', string='Marca', required=True)
    model = fields.Char(string='Modelo', required=True)
    equipment_type = fields.Char(string='Tipo de equipo', help='Monitor, ventilador, bomba de infusión...')
    image = fields.Image(max_width=512, max_height=512)
    notes = fields.Text()
    product_ids = fields.Many2many(
        'product.template', 'biotex_product_equipment_rel', 'equipment_id', 'product_tmpl_id',
        string='Insumos compatibles')

    @api.depends('brand_id.name', 'model', 'equipment_type')
    def _compute_display_name(self):
        for eq in self:
            parts = [eq.brand_id.name or '', eq.model or '']
            if eq.equipment_type:
                parts.append('(%s)' % eq.equipment_type)
            eq.display_name = ' '.join(p for p in parts if p)
