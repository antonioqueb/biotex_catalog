from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from ..models.biotex_classification import BiotexClassificationSessionLine


@tagged('post_install', '-at_install')
class TestProductSequence(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        source_family = cls.env['product.category'].search([
            ('biotex_level', '=', 'family'), ('biotex_classifier_ids', '!=', False)], limit=1)
        cls.classifier = source_family.biotex_classifier_ids[0]
        cls.family = cls.env['product.category'].create({
            'name': 'Sequence test family', 'biotex_level': 'family', 'biotex_code': 'TSQ',
            'biotex_group_id': source_family.biotex_group_id.id,
            'biotex_classifier_ids': [(6, 0, cls.classifier.ids)],
        })
        cls.brand = cls.env['biotex.brand'].create({'name': 'Sequence test brand', 'code': 'CNSQ'})
        cls.prefix = '%s-TSQ-%s-CNSQ' % (cls.family.biotex_group_id.code, cls.classifier.code)  # GG-FFF-CCC-MMMM
        cls.counter = cls.env['biotex.product.sequence']
        cls.operator = new_test_user(cls.env(context={**cls.env.context, 'no_reset_password': True}),
                                    login='product_sequence_test_operator', groups='biotex_catalog.group_catalog_classifier')

    def product(self, **extra):
        return self.env['product.template'].create(dict({
            'name': 'Sequence fixture', 'categ_id': self.family.id,
            'biotex_classifier_id': self.classifier.id, 'biotex_brand_id': self.brand.id,
        }, **extra))

    def session(self):
        return self.env['biotex.classification.session'].with_user(self.operator).create({
            'group_id': self.family.biotex_group_id.id, 'family_id': self.family.id,
            'classifier_id': self.classifier.id, 'brand_id': self.brand.id,
        })

    def test_archived_suffix_is_used_when_metadata_is_missing(self):
        self.product(default_code=self.prefix + '-42', biotex_consecutive=0, active=False)
        product = self.product()
        self.assertEqual(product.with_user(self.operator).biotex_preview_clave(), self.prefix + '-43')
        product.with_user(self.operator).action_assign_clave()
        self.assertEqual(product.default_code, self.prefix + '-43')

    def test_larger_stored_counter_is_respected(self):
        product = self.product(default_code=self.prefix + '-04', biotex_consecutive=70)
        self.assertEqual(self.counter._next(self.prefix), 71)
        product.default_code = 'RENAMED-LEGACY'
        self.assertEqual(self.counter._next(self.prefix), 71)

    def test_preview_does_not_consume_numbers(self):
        product = self.product()
        self.assertEqual(product.biotex_preview_clave(), self.prefix + '-01')
        self.assertEqual(product.biotex_preview_clave(), self.prefix + '-01')
        product.action_assign_clave()
        self.assertEqual(product.default_code, self.prefix + '-01')
        product.action_assign_clave()
        self.assertEqual(product.default_code, self.prefix + '-01')

    def test_individual_and_multiple_sessions_share_counter(self):
        first, second = self.session(), self.session()
        first.workspace_add_products(self.product().ids)
        individual = self.product()
        individual.with_user(self.operator).action_assign_clave()
        second.workspace_add_products(self.product().ids)
        self.assertEqual(first.line_ids.consecutive, 1)
        self.assertEqual(individual.default_code, self.prefix + '-02')
        self.assertEqual(second.line_ids.consecutive, 3)

    def test_removed_cancelled_and_deleted_reservations_are_not_reused(self):
        session = self.session()
        session.workspace_add_products(self.product().ids)
        session.workspace_remove_line(session.line_ids.id)
        session.workspace_add_products(self.product().ids)
        self.assertEqual(session.line_ids.consecutive, 2)
        session.action_cancel()
        another = self.session()
        another.workspace_add_products(self.product().ids)
        self.assertEqual(another.line_ids.consecutive, 3)
        another.unlink()
        self.assertEqual(self.counter._next(self.prefix), 4)
        session.action_draft()
        self.assertEqual(session.line_ids.consecutive, 2)

    def test_deleted_or_renamed_products_do_not_reset_counter(self):
        product = self.product(default_code=self.prefix + '-55')
        product.unlink()
        self.assertEqual(self.counter._next(self.prefix), 56)
        product = self.product(default_code=self.prefix + '-56')
        product.default_code = 'RECLASSIFIED-LEGACY'
        self.assertEqual(self.counter._next(self.prefix), 57)

    def test_existing_reference_is_preserved_even_when_not_the_last(self):
        product = self.product(default_code=self.prefix + '-05', biotex_consecutive=0)
        self.product(default_code=self.prefix + '-20')
        preview = product.biotex_classifier_preview({
            'id': product.id, 'biotex_family_id': self.family.id,
            'biotex_classifier_id': self.classifier.id, 'biotex_brand_id': self.brand.id})
        self.assertEqual(preview['clave'], self.prefix + '-05')
        product.action_assign_clave()
        self.assertEqual(product.default_code, self.prefix + '-05')
        self.assertEqual(product.biotex_consecutive, 5)

    def test_direct_duplicate_is_rejected_even_if_archived(self):
        self.product(default_code=self.prefix + '-07', active=False)
        with self.assertRaisesRegex(ValidationError, 'ya está utilizada'), self.cr.savepoint():
            self.product(default_code=self.prefix + '-07')

    def test_reservations_cannot_be_manually_overwritten(self):
        session = self.session()
        session.workspace_add_products(self.product().ids)
        with self.assertRaises(UserError):
            session.line_ids.write({'consecutive': 1})

    def test_legacy_colliding_draft_is_repaired_before_confirmation(self):
        first, second = self.session(), self.session()
        first.workspace_add_products(self.product().ids)
        second.workspace_add_products(self.product().ids)
        # Simulate a draft persisted by the previous allocator.
        super(BiotexClassificationSessionLine, second.line_ids).write({'consecutive': 1})
        preview = second.workspace_confirmation_preview()
        self.assertEqual(second.line_ids.consecutive, 3)
        second.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(second.line_ids.product_id.default_code, self.prefix + '-03')
        self.assertEqual(first.line_ids.consecutive, 1)

    def test_catalog_collision_invalidates_review_and_requires_new_revision(self):
        session = self.session()
        session.workspace_add_products(self.product().ids)
        preview = session.workspace_confirmation_preview()
        self.product(default_code=self.prefix + '-01')
        with self.assertRaisesRegex(UserError, 'cambió desde la revisión'):
            session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(session.state, 'draft')
        self.assertFalse(session.line_ids.product_id.default_code)
        preview = session.workspace_confirmation_preview()
        session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(session.line_ids.product_id.default_code, self.prefix + '-02')

    def test_prefix_change_uses_new_prefix_floor_and_preserves_old_watermark(self):
        self.product(default_code=self.prefix + '-40')
        session = self.session()
        session.workspace_add_products(self.product().ids)
        other_brand = self.env['biotex.brand'].create({'name': 'Alternate sequence brand', 'code': 'CNSR'})
        other_prefix = self.prefix.replace('CNSQ', 'CNSR')
        self.product(default_code=other_prefix + '-03', biotex_brand_id=other_brand.id)
        session.write({'brand_id': other_brand.id})
        self.assertEqual(session.line_ids.reference, other_prefix + '-04')
        self.assertEqual(self.counter._next(self.prefix), 42)

    def test_reorder_continues_after_archived_products_and_reservations(self):
        a = self.product(name='A sequence fixture', default_code=self.prefix + '-01')
        b = self.product(name='B sequence fixture', default_code=self.prefix + '-02')
        self.product(default_code=self.prefix + '-09', active=False)
        session = self.session()
        # `a` ya tiene clave de esta clasificación: entra conservando su referencia, sin reservar número.
        session.workspace_add_products(a.ids)
        self.assertTrue(session.line_ids.preserve_reference)
        self.assertEqual(session.line_ids.consecutive, 0)
        # Una reserva de un producto nuevo sí sigue bloqueada mientras la familia se reordena.
        session.workspace_add_products(self.product().ids)
        self.assertEqual(session.line_ids.mapped('consecutive'), [0, 10])
        wizard = self.env['biotex.reorder.wizard'].with_user(self.env.ref('base.user_admin')).create({'product_ids': [(6, 0, (a | b).ids)]})
        self.assertIn(self.prefix + '-11', str(wizard.preview))
        wizard.action_apply()
        self.assertEqual(a.default_code, self.prefix + '-11')
        self.assertEqual(b.default_code, self.prefix + '-12')
        # La línea conservada sigue a la clave actual del producto.
        self.assertEqual(session.line_ids.filtered('preserve_reference').reference, self.prefix + '-11')

    def test_counter_is_shared_across_companies(self):
        other_company = self.env['res.company'].search([('id', '!=', self.env.company.id)], limit=1)
        self.assertTrue(other_company)
        self.product(default_code=self.prefix + '-31', company_id=other_company.id, active=False)
        session = self.session()
        session.workspace_add_products(self.product().ids)
        self.assertEqual(session.line_ids.consecutive, 32)
