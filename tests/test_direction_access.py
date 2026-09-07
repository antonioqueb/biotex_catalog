"""A user assigned only Dirección must include every catalog function."""
import itertools
import string

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestDirectionAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        context = cls.env(context={**cls.env.context, 'no_reset_password': True})
        cls.director = new_test_user(context, login='catalog_direction_access_test', groups='biotex_base.group_biotex_direction')
        cls.classifier = new_test_user(context, login='catalog_classifier_access_test', groups='biotex_catalog.group_catalog_classifier')

    def test_direction_inherits_classifier_and_business_managers(self):
        for xmlid in ('biotex_catalog.group_catalog_classifier', 'biotex_base.group_biotex_coordinator',
                      'biotex_base.group_biotex_purchase', 'biotex_base.group_biotex_payments',
                      'biotex_base.group_biotex_accounting', 'stock.group_stock_manager',
                      'purchase.group_purchase_manager', 'base.group_partner_manager'):
            self.assertTrue(self.director.has_group(xmlid), xmlid)
        self.assertFalse(self.director.has_group('base.group_system'))

    def test_direction_sees_every_catalog_action(self):
        visible = self.env['ir.ui.menu'].with_user(self.director)._visible_menu_ids()
        menus = self.env['ir.model.data'].search([('module', '=', 'biotex_catalog'), ('model', '=', 'ir.ui.menu')])
        for data in menus:
            menu = self.env['ir.ui.menu'].browse(data.res_id)
            if menu.action:
                self.assertIn(menu.id, visible, data.complete_name)

    def test_direction_has_full_catalog_and_configuration_access(self):
        for name in ('biotex.division', 'biotex.group', 'biotex.classifier', 'product.category',
                     'biotex.brand', 'biotex.specialty', 'biotex.equipment', 'biotex.generic',
                     'biotex.mt.subclass', 'biotex.package.type', 'biotex.product.synonym',
                     'product.template', 'product.product', 'product.tag',
                     'biotex.classification.session', 'biotex.classification.session.line',
                     'biotex.reorder.wizard', 'biotex.delegation', 'biotex.exception',
                     'stock.warehouse', 'stock.location', 'res.partner'):
            for operation in ('read', 'create', 'write', 'unlink'):
                self.env[name].with_user(self.director).check_access(operation)

    def test_direction_can_create_and_edit_taxonomy_products_and_sessions(self):
        env = self.env(user=self.director.id)
        code = next(''.join(chars) for chars in itertools.product(string.ascii_uppercase, repeat=2)
                    if not env['biotex.group'].with_context(active_test=False).search_count([('code', '=', ''.join(chars))]))
        division = env['biotex.division'].create({'name': 'Direction access test', 'code': 'DRA'})
        group = env['biotex.group'].create({'name': 'Direction group', 'code': code, 'division_id': division.id})
        classifier = env['biotex.classifier'].create({'name': 'Direction classifier', 'code': 'DIR', 'group_id': group.id})
        family = env['product.category'].create({'name': 'Direction family', 'biotex_level': 'family', 'biotex_group_id': group.id,
                                               'biotex_code': 'DIR', 'biotex_classifier_ids': [(6, 0, classifier.ids)]})
        brand = env['biotex.brand'].create({'name': 'Direction test brand', 'code': 'DRAZ'})
        product = env['product.template'].create({'name': 'Direction test product', 'categ_id': family.id,
                                                'biotex_brand_id': brand.id, 'biotex_classifier_id': classifier.id})
        group.name = 'Updated direction group'
        family.name = 'Updated direction family'
        product.name = 'Updated direction product'
        session = env['biotex.classification.session'].create({'group_id': group.id, 'family_id': family.id,
                                                              'classifier_id': classifier.id, 'brand_id': brand.id})
        session.workspace_search_products(query='Updated direction product')
        self.assertTrue(group.tag_id)
        self.assertEqual(family.name, 'Updated direction family')
        self.assertTrue(session.id)
        session.unlink()
        product.unlink()

    def test_classifier_does_not_gain_direction_or_configuration_management(self):
        self.assertFalse(self.classifier.has_group('biotex_base.group_biotex_direction'))
        self.assertFalse(self.classifier.has_group('stock.group_stock_manager'))
        with self.assertRaises(AccessError):
            self.env['biotex.group'].with_user(self.classifier).create({'name': 'Not allowed', 'code': 'ZZ'})
        with self.assertRaises(AccessError):
            self.env['product.category'].with_user(self.classifier).create({'name': 'Not allowed'})
