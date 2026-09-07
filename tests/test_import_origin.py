from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestImportOrigin(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        context = dict(cls.env.context, no_reset_password=True, mail_create_nosubscribe=True)
        cls.operator = new_test_user(cls.env(context=context), login='import_origin_test_operator',
                                     groups='biotex_catalog.group_catalog_classifier')

    def test_external_manufacturer_reference_is_not_product_identity(self):
        products = self.env['product.template'].create([
            {'name': 'Reference scope fixture A', 'biotex_reference': 'SHARED-EXTERNAL-REF'},
            {'name': 'Reference scope fixture B', 'biotex_reference': 'SHARED-EXTERNAL-REF'},
        ])
        self.assertEqual(len(products), 2)
        self.assertNotEqual(products[0].id, products[1].id)

    def test_actual_source_sheet_and_absent_legacy_fields(self):
        product = self.env['product.template'].create({
            'name': 'New sheet origin fixture', 'biotex_import_sha256': 'new-source',
            'biotex_import_source': {'worksheet': 'NUEVAS', 'columns': ['DESCRIPCION'],
                                     'rows': [{'worksheet_row': 2, 'values': ['New item']}]},
        })
        self.assertIn('Hoja NUEVAS', str(product.biotex_import_detail))
        self.assertNotIn('20_REMAPEO', str(product.biotex_import_detail))
        self.assertFalse(product.biotex_legacy_code)
        self.assertFalse(product.biotex_alt_code)
        product.biotex_import_source = {'columns': [], 'rows': [{'worksheet_row': 6, 'values': []}]}
        self.assertIn('Hoja 20_REMAPEO', str(product.biotex_import_detail))

    def test_provenance_and_pending_use_cannot_be_overwritten(self):
        product = self.env['product.template'].create({
            'name': 'Pending origin fixture', 'biotex_import_sha256': 'fixture-source-hash',
            'biotex_import_source': {'rows': [{'values': ['original reference']} ]},
            'biotex_import_status': 'review', 'sale_ok': False, 'purchase_ok': False,
        }).with_user(self.operator)
        for values in ({'biotex_import_source': {}}, {'biotex_import_status': 'validated'}):
            with self.assertRaises(AccessError): product.write(values)
        with self.assertRaises(UserError): product.write({'sale_ok': True})
        with self.assertRaises(UserError): product.action_validate_import()
        self.assertEqual(product.biotex_import_source['rows'][0]['values'], ['original reference'])
