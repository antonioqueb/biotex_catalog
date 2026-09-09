"""Check the menus delivered to the web client, including their parent apps."""
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestClassifierNavigation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        context = cls.env(context={**cls.env.context, 'no_reset_password': True})
        cls.director = new_test_user(context, login='classifier_navigation_direction',
                                     groups='biotex_base.group_biotex_direction')
        cls.inventory_user = new_test_user(context, login='classifier_navigation_inventory',
                                           groups='stock.group_stock_user')

    def test_direction_opens_classifier_from_catalog_and_inventory(self):
        menus = self.env['ir.ui.menu'].with_user(self.director).load_menus(False)
        action = self.env.ref('biotex_catalog.action_biotex_classification_workspace')
        for menu_xmlid, app_xmlid in (
            ('biotex_catalog.menu_biotex_classification_workspace', 'biotex_catalog.menu_catalog_root'),
            ('biotex_catalog.menu_stock_classification_workspace', 'stock.menu_stock_root'),
        ):
            menu = self.env.ref(menu_xmlid)
            self.assertIn(menu.id, menus, menu_xmlid)
            self.assertEqual(menus[menu.id]['app_id'], self.env.ref(app_xmlid).id)
            self.assertEqual(menus[menu.id]['action_id'], action.id)
        workspace = self.env['biotex.classification.session'].with_user(self.director)
        self.assertFalse(workspace.env.su)
        self.assertIn('tree', workspace.workspace_bootstrap(False))

    def test_inventory_user_does_not_gain_classifier_access(self):
        self.assertFalse(self.inventory_user.has_group('biotex_catalog.group_catalog_classifier'))
        menus = self.env['ir.ui.menu'].with_user(self.inventory_user).load_menus(False)
        self.assertNotIn(self.env.ref('biotex_catalog.menu_stock_classification_workspace').id, menus)
        self.assertFalse(self.env['biotex.classification.session'].with_user(self.inventory_user).has_access('read'))
