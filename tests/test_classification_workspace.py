from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestClassificationWorkspace(TransactionCase):
    """Exercise the persistent wizard with a warehouse classifier, not superuser permissions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(cls.env, login='classification_test_operator',
                                    groups='biotex_catalog.group_catalog_classifier')
        cls.family = cls.env['product.category'].search([
            ('biotex_level', '=', 'family'), ('biotex_classifier_ids', '!=', False)], limit=1)
        cls.brand = cls.env['biotex.brand'].create({'name': 'Workspace test brand', 'code': 'WSTX'})
        cls.products = cls.env['product.template'].create([
            {'name': 'Workspace fixture %03d' % n, 'default_code': 'BEFORE-%03d' % n}
            for n in range(25)
        ])

    def new_session(self):
        return self.env['biotex.classification.session'].with_user(self.operator).create({
            'group_id': self.family.biotex_group_id.id,
            'family_id': self.family.id,
            'classifier_id': self.family.biotex_classifier_ids[0].id,
            'brand_id': self.brand.id,
        })

    def test_search_excludes_added_before_count_and_pagination(self):
        session = self.new_session()
        first = session.workspace_search_products('Workspace fixture', limit=1000)
        self.assertEqual(first['total'], 25)
        self.assertEqual(len(first['records']), 20)
        product = self.products[0]
        session.workspace_add_products([product.id, product.id])
        session.workspace_add_products([product.id])
        self.assertEqual(len(session.line_ids), 1)
        second = session.workspace_search_products('Workspace fixture')
        last = session.workspace_search_products('Workspace fixture', offset=20)
        self.assertEqual(second['total'], 24)
        self.assertEqual(len(second['records']), 20)
        self.assertEqual(len(last['records']), 4)
        self.assertNotIn(product.id, [p['id'] for p in second['records'] + last['records']])
        session.workspace_remove_line(session.line_ids.id)
        self.assertEqual(session.workspace_search_products('Workspace fixture')['total'], 25)
        self.assertEqual(product.default_code, 'BEFORE-000')

    def test_last_page_moves_back_after_removing_available_results(self):
        session = self.new_session()
        session.workspace_add_products(self.products[20:].ids)
        result = session.workspace_search_products('Workspace fixture', offset=20)
        self.assertEqual(result['offset'], 0)
        self.assertEqual(len(result['records']), 20)

    def test_reclassification_requires_current_review_and_keeps_identity(self):
        session = self.new_session()
        product = self.products[0]
        variant_ids = product.product_variant_ids.ids
        session.workspace_add_products([product.id])
        with self.assertRaisesRegex(UserError, 'referencias existentes'):
            session.workspace_confirm()
        self.assertEqual(product.default_code, 'BEFORE-000')
        preview = session.workspace_confirmation_preview()
        self.assertEqual(preview['changes'][0]['before'], 'BEFORE-000')
        session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(session.state, 'confirmed')
        self.assertEqual(product.product_variant_ids.ids, variant_ids)
        self.assertEqual(product.default_code, session.line_ids.reference)
        self.assertEqual(session.line_ids.applied_reference_before, 'BEFORE-000')
        self.assertEqual(session.line_ids.applied_reference_after, product.default_code)
        self.assertEqual(session.line_ids.applied_by_id, self.operator)
        self.assertTrue(session.line_ids.applied_on)
        note = product.message_ids.filtered(lambda m: 'BEFORE-000' in str(m.body))
        self.assertEqual(len(note), 1)
        self.assertEqual(note.author_id, self.operator.partner_id)
        for operation in (lambda: session.write({'state': 'draft'}),
                          lambda: session.line_ids.write({'new_name': 'Overwrite history'}),
                          lambda: session.line_ids.unlink(), lambda: session.unlink()):
            with self.assertRaises(UserError):
                operation()

    def test_changed_product_invalidates_acknowledgement(self):
        session = self.new_session()
        product = self.products[0]
        session.workspace_add_products([product.id])
        preview = session.workspace_confirmation_preview()
        product.default_code = 'CHANGED-ELSEWHERE'
        with self.assertRaisesRegex(UserError, 'cambió desde la revisión'):
            session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(session.state, 'draft')
        self.assertEqual(product.default_code, 'CHANGED-ELSEWHERE')
        self.assertFalse(session.line_ids.applied_on)

    def test_changed_draft_invalidates_acknowledgement(self):
        session = self.new_session()
        session.workspace_add_products([self.products[0].id])
        preview = session.workspace_confirmation_preview()
        session.workspace_update_line(session.line_ids.id, {'new_name': 'A revised product description'})
        with self.assertRaisesRegex(UserError, 'cambió desde la revisión'):
            session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(self.products[0].default_code, 'BEFORE-000')

    def test_changing_classification_reassigns_preview_and_reorder_keeps_numbers(self):
        session = self.new_session()
        session.workspace_add_products(self.products[:2].ids)
        numbers = {line.id: line.consecutive for line in session.line_ids}
        session.workspace_reorder(session.line_ids[::-1].ids)
        self.assertEqual({line.id: line.consecutive for line in session.line_ids}, numbers)
        other_brand = self.env['biotex.brand'].create({'name': 'Second workspace brand', 'code': 'WSU2'})
        session.workspace_set_classification(session.id, {
            'group_id': session.group_id.id, 'family_id': session.family_id.id,
            'classifier_id': session.classifier_id.id, 'brand_id': other_brand.id})
        self.assertTrue(all('WSU2' in line.reference for line in session.line_ids))
        self.assertEqual(self.products[0].default_code, 'BEFORE-000')
