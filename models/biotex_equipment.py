from odoo import api, fields, models


class BiotexEquipment(models.Model):
    """Equipo al que se conecta el consumible. Puede ser un tipo genérico del esquema (EQ-MON Monitor de signos vitales)
    o un equipo concreto con marca y modelo (Mindray BeneView T8)."""
    _name = 'biotex.equipment'
    _description = 'Equipo relacionado'
    _order = 'code, brand_id, model'

    code = fields.Char(string='Código', size=8, help='Ej. EQ-MON. Vacío para equipos concretos con marca y modelo.')
    name = fields.Char(string='Tipo de equipo', required=True, help='Monitor de signos vitales, electrocardiógrafo, ventilador...')
    brand_id = fields.Many2one('biotex.brand', string='Marca')
    model = fields.Char(string='Modelo')
    parent_id = fields.Many2one('biotex.equipment', string='Tipo genérico', domain=[('brand_id', '=', False)], help='Equipo concreto → su tipo del esquema.')
    image = fields.Image(max_width=512, max_height=512)
    notes = fields.Text()
    active = fields.Boolean(default=True)
    product_ids = fields.Many2many('product.template', 'biotex_product_equipment_rel', 'equipment_id', 'product_tmpl_id', string='Insumos compatibles')
    product_count = fields.Integer(compute='_compute_product_count')

    @api.depends('code', 'name', 'brand_id.name', 'model')
    def _compute_display_name(self):
        for eq in self:
            if eq.brand_id or eq.model:
                eq.display_name = ' '.join(x for x in (eq.brand_id.name, eq.model, '(%s)' % eq.name if eq.name else '') if x)
            else:
                eq.display_name = '%s · %s' % (eq.code, eq.name) if eq.code else eq.name

    def _compute_product_count(self):
        for eq in self:
            eq.product_count = len(eq.product_ids)
