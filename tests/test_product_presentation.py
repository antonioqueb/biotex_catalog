"""Alta de productos con presentaciones (``product.uom``) desde el formulario y desde el asistente.

Reproduce el bloqueo "Capture las presentaciones en un producto sin variantes." al crear un producto nuevo
(el inverso del campo calculado corría antes de que existiera la variante) y cubre el código de barras opcional.
"""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestProductPresentation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.unit = cls.env.ref('uom.product_uom_unit')

    def presentation(self, **values):
        return Command.create({'uom_id': self.unit.id, **values})

    def test_create_template_with_presentation_in_same_call(self):
        """El caso del reporte: presentación capturada en el mismo guardado del alta (sin código)."""
        tmpl = self.env['product.template'].create({
            'name': 'Presentación en el alta', 'uom_id': self.unit.id,
            'biotex_presentation_ids': [self.presentation()],
        })
        self.assertEqual(len(tmpl.product_variant_ids), 1)
        self.assertEqual(len(tmpl.biotex_presentation_ids), 1)
        self.assertEqual(tmpl.biotex_presentation_ids.product_id, tmpl.product_variant_id)
        self.assertFalse(tmpl.biotex_presentation_ids.barcode, 'el código de barras ya no es obligatorio')
        self.assertIn(self.unit, tmpl.uom_ids)

    def test_create_template_without_presentation_and_with_empty_list(self):
        """Alta mínima, y alta con el campo enviado vacío tal como lo manda el formulario sin tocarlo."""
        minimal = self.env['product.template'].create({'name': 'Alta mínima'})
        self.assertEqual(len(minimal.product_variant_ids), 1)
        self.assertFalse(minimal.biotex_presentation_ids)
        sent_empty = self.env['product.template'].create({'name': 'Alta con lista vacía', 'biotex_presentation_ids': []})
        self.assertEqual(len(sent_empty.product_variant_ids), 1)
        self.assertFalse(sent_empty.biotex_presentation_ids)

    def test_add_presentation_after_save_still_works(self):
        """El rodeo que usaban los operadores (guardar y luego capturar) sigue funcionando, con y sin código."""
        tmpl = self.env['product.template'].create({'name': 'Dos pasos', 'uom_id': self.unit.id})
        tmpl.write({'biotex_presentation_ids': [self.presentation(barcode='EAN-TEST-001'), self.presentation()]})
        self.assertEqual(sorted(tmpl.biotex_presentation_ids.mapped('barcode'), key=str), [False, 'EAN-TEST-001'])
        self.assertEqual(tmpl.product_variant_id.product_uom_ids, tmpl.biotex_presentation_ids)

    def test_presentation_blocked_on_multi_variant_template(self):
        """La regla real se conserva: con varias variantes por atributos no hay presentaciones a nivel plantilla."""
        attribute = self.env['product.attribute'].create({'name': 'Talla prueba', 'value_ids': [Command.create({'name': 'M'}), Command.create({'name': 'L'})]})
        lines = [Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})]
        with self.assertRaisesRegex(UserError, 'variantes por atributos'), self.cr.savepoint():
            self.env['product.template'].create({'name': 'Multi variante', 'attribute_line_ids': lines, 'biotex_presentation_ids': [self.presentation()]})
        multi = self.env['product.template'].create({'name': 'Multi variante sin presentación', 'attribute_line_ids': lines})
        self.assertEqual(len(multi.product_variant_ids), 2)
        with self.assertRaisesRegex(UserError, 'variantes por atributos'), self.cr.savepoint():
            multi.write({'biotex_presentation_ids': [self.presentation()]})
        # los scripts de importación pueden omitir la comprobación
        multi.with_context(biotex_skip_presentation_check=True).write({'biotex_presentation_ids': [self.presentation()]})
        self.assertFalse(multi.product_variant_ids.product_uom_ids, 'omitida: no se escribe nada')

    @mute_logger('odoo.sql_db')
    def test_barcode_optional_but_unique_when_present(self):
        """Varias presentaciones sin código conviven; un código repetido sigue rechazado por la restricción del core."""
        Template = self.env['product.template']
        Template.create({'name': 'A', 'biotex_presentation_ids': [self.presentation(barcode='EAN-DUP-001')]})
        b = Template.create({'name': 'B sin código', 'biotex_presentation_ids': [self.presentation()]})
        c = Template.create({'name': 'C sin código', 'biotex_presentation_ids': [self.presentation()]})
        self.assertFalse(b.biotex_presentation_ids.barcode or c.biotex_presentation_ids.barcode)
        with self.assertRaises(Exception), self.cr.savepoint():
            Template.create({'name': 'C duplicado', 'biotex_presentation_ids': [self.presentation(barcode='EAN-DUP-001')]})

    def test_wizard_rows_accept_missing_barcode_and_keep_the_record(self):
        """El asistente de clasificación acepta empacados sin código y conserva el registro al volver a guardar."""
        tmpl = self.env['product.template'].create({'name': 'Empacado sin código', 'uom_id': self.unit.id})
        tmpl._biotex_set_presentations([{'name': 'caja 20', 'quantity': 20, 'barcode': ''}, {'name': 'caja 50', 'quantity': 50, 'barcode': 'EAN-CAJA-50'}])
        rows = tmpl.biotex_presentation_ids
        self.assertEqual(sorted(rows.mapped('biotex_quantity')), [20, 50])
        without = rows.filtered(lambda r: not r.barcode)
        self.assertEqual(without.uom_id.name, 'CAJA 20')
        tmpl._biotex_set_presentations([{'name': 'caja 20', 'quantity': 20, 'barcode': ''}, {'name': 'caja 50', 'quantity': 50, 'barcode': 'EAN-CAJA-50'}])
        self.assertEqual(tmpl.biotex_presentation_ids.filtered(lambda r: not r.barcode), without, 'mismo registro, sin recrear')
        data = {row['name']: row for row in tmpl._biotex_presentation_data()}
        self.assertFalse(data['CAJA 20']['barcode'])
        tmpl._biotex_set_presentations([{'name': 'caja 50', 'quantity': 50, 'barcode': 'EAN-CAJA-50'}])
        self.assertFalse(tmpl.biotex_presentation_ids.filtered(lambda r: not r.barcode), 'el empacado sin código omitido se elimina')
