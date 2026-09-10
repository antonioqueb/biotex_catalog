from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestClassificationWorkspace(TransactionCase):
    """Exercise the persistent wizard with a warehouse classifier, not superuser permissions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        test_env = cls.env(context={**cls.env.context, 'no_reset_password': True})
        cls.operator = new_test_user(test_env, login='classification_test_operator',
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

    def test_editor_multi_country_equipment_and_brand_manufacturer_suggestion(self):
        """El modal recibe el fabricante de la marca como sugerencia y guarda varios países y equipos."""
        manufacturer = self.env['res.partner'].create({'name': 'Editor test manufacturer', 'is_company': True})
        self.brand.manufacturer_id = manufacturer
        countries = self.env['res.country'].search([], limit=2, order='id')
        equipments = self.env['biotex.equipment'].search([], limit=2, order='id')
        if len(equipments) < 2:
            equipments = self.env['biotex.equipment'].create([{'name': 'Editor equipment A'}, {'name': 'Editor equipment B'}])
        product = self.products[3]
        product.write({'biotex_country_id': countries[0].id, 'biotex_main_equipment_id': equipments[0].id})
        session = self.new_session()
        session.workspace_add_products([product.id])
        line = session.line_ids
        self.assertEqual(line.country_ids, countries[0])
        self.assertEqual(line.equipment_ids, equipments[0])
        detail = session.workspace_line_detail(line.id)
        self.assertEqual(detail['brand_manufacturer_id'], manufacturer.id)
        self.assertEqual([c['id'] for c in detail['line']['country_ids']], [countries[0].id])
        self.assertFalse(detail['line']['manufacturer_id'])  # la sugerencia no se guarda hasta que el usuario guarda
        session.workspace_update_line(line.id, {
            'new_name': 'EDITOR MULTI TEST', 'base_name': 'EDITOR MULTI TEST', 'uom_id': line.uom_id.id,
            'country_ids': [countries[1].id, countries[0].id, countries[0].id],
            'equipment_ids': [equipments[1].id, equipments[0].id], 'manufacturer_id': manufacturer.id,
        })
        self.assertEqual(line.country_ids, countries[1] | countries[0])
        self.assertEqual(line.country_id, countries[1], 'el primero elegido es el principal')
        self.assertEqual(line.equipment_id, equipments[1])
        preview = session.workspace_confirmation_preview()
        session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(product.biotex_country_id, countries[1])
        self.assertEqual(product.biotex_country_ids, countries[1] | countries[0])
        self.assertEqual(product.biotex_main_equipment_id, equipments[1])
        self.assertEqual(product.biotex_equipment_ids, equipments[0] | equipments[1])
        self.assertEqual(product.biotex_manufacturer_id, manufacturer)

    def test_specialties_multi_and_manufacturer_suggestion_never_overrides_manual_value(self):
        suggested = self.env['res.partner'].create({'name': 'Brand suggested manufacturer', 'is_company': True})
        chosen = self.env['res.partner'].create({'name': 'Manually chosen manufacturer', 'is_company': True})
        self.brand.manufacturer_id = suggested
        specialties = self.env['biotex.specialty'].search([], limit=2, order='id')
        if len(specialties) < 2:
            specialties = self.env['biotex.specialty'].create([{'name': 'Flow specialty A', 'code': 'FSA'}, {'name': 'Flow specialty B', 'code': 'FSB'}])
        product = self.products[4]
        session = self.new_session()
        session.workspace_add_products([product.id])
        line = session.line_ids
        self.assertEqual(line.manufacturer_id, suggested, 'sin fabricante en la ficha se toma el de la marca')
        self.assertFalse(line.manufacturer_manual)
        # el usuario elige otro: queda marcado como capturado a mano
        session.workspace_update_line(line.id, {'new_name': line.new_name, 'uom_id': line.uom_id.id, 'manufacturer_id': chosen.id,
                                                'specialty_ids': [specialties[1].id, specialties[0].id]})
        self.assertTrue(line.manufacturer_manual)
        self.assertEqual(line.specialty_ids, specialties[1] | specialties[0])
        self.assertEqual(line.specialty_id, specialties[1], 'la primera elegida es la principal')
        # el usuario lo vacía: tampoco se vuelve a sugerir, ni al recalcular por cambio de marca
        session.workspace_update_line(line.id, {'new_name': line.new_name, 'uom_id': line.uom_id.id, 'manufacturer_id': False})
        self.assertFalse(line.manufacturer_id)
        self.assertTrue(line.manufacturer_manual)
        other_brand = self.env['biotex.brand'].create({'name': 'Suggesting brand', 'code': 'WSU3', 'manufacturer_id': suggested.id})
        session.write({'brand_id': other_brand.id})
        self.assertFalse(line.manufacturer_id, 'un valor vaciado a mano no se rellena')
        detail = session.workspace_line_detail(line.id)['line']
        self.assertTrue(detail['manufacturer_manual'])
        # una línea nunca tocada sí recibe la sugerencia al fijar la marca
        untouched = self.products[5]
        session.workspace_add_products([untouched.id])
        self.assertEqual(session.line_ids.filtered(lambda l: l.product_id == untouched).manufacturer_id, suggested)
        preview = session.workspace_confirmation_preview()
        session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(product.biotex_main_specialty_id, specialties[1])
        self.assertEqual(product.biotex_specialty_ids, specialties[0] | specialties[1])
        self.assertFalse(product.biotex_manufacturer_id)
