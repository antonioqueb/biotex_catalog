"""Apertura desde la lista de productos, bloqueo entre sesiones, reclasificación sin cambiar clave y orden del folio."""
from urllib.parse import unquote

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestClassificationFlow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        source_family = cls.env['product.category'].search([('biotex_level', '=', 'family'), ('biotex_classifier_ids', '!=', False)], limit=1)
        cls.classifier = source_family.biotex_classifier_ids[0]
        cls.group = source_family.biotex_group_id
        cls.family = cls.env['product.category'].create({
            'name': 'Flow test family', 'biotex_level': 'family', 'biotex_code': 'TFL',
            'biotex_group_id': cls.group.id, 'biotex_classifier_ids': [(6, 0, cls.classifier.ids)]})
        cls.brand = cls.env['biotex.brand'].create({'name': 'Flow test brand', 'code': 'FLOW'})
        cls.other_brand = cls.env['biotex.brand'].create({'name': 'Flow other brand', 'code': 'FLOX'})
        cls.prefix = '%s-TFL-%s-FLOW' % (cls.group.code, cls.classifier.code)
        ctx = cls.env(context={**cls.env.context, 'no_reset_password': True})
        cls.operator = new_test_user(ctx, login='flow_operator', groups='biotex_catalog.group_catalog_classifier')
        cls.colleague = new_test_user(ctx, login='flow_colleague', groups='biotex_catalog.group_catalog_classifier')

    def product(self, **extra):
        return self.env['product.template'].create(dict({'name': 'Flow fixture'}, **extra))

    def classified_product(self, code, **extra):
        return self.product(categ_id=self.family.id, biotex_classifier_id=self.classifier.id, biotex_brand_id=self.brand.id,
                            default_code=code, **extra)

    def session(self, user=None, **vals):
        return self.env['biotex.classification.session'].with_user(user or self.operator).create({
            'group_id': self.group.id, 'family_id': self.family.id, 'classifier_id': self.classifier.id,
            'brand_id': self.brand.id, **vals})

    def confirm(self, session):
        preview = session.workspace_confirmation_preview()
        session.workspace_confirm(expected_revision=preview['revision'])

    # ------------------------------------------------------------ orden del folio
    def test_class_code_and_product_key_follow_group_family_classifier_brand(self):
        session = self.session()
        self.assertEqual(session.class_code, self.prefix)
        product = self.product(categ_id=self.family.id, biotex_classifier_id=self.classifier.id, biotex_brand_id=self.brand.id)
        session.workspace_add_products(product.ids)
        self.assertEqual(session.line_ids.reference, self.prefix + '-01')
        self.confirm(session)
        self.assertEqual(product.default_code, self.prefix + '-01')
        counter = self.env['biotex.product.sequence']
        legacy = '%s-FLOW-TFL-%s-07' % (self.group.code, self.classifier.code)
        self.assertEqual(counter._split_code(legacy), ('%s-FLOW-TFL-%s' % (self.group.code, self.classifier.code), 7), 'las claves anteriores siguen reconociéndose')
        self.assertEqual(counter._split_code(self.prefix + '-12'), (self.prefix, 12))

    # ------------------------------------------------------------ reclasificación
    def test_reclassifying_a_classified_product_keeps_reference_and_names(self):
        product = self.classified_product(self.prefix + '-05', name='PRODUCTO YA CLASIFICADO')
        legacy = self.classified_product('%s-FLOW-TFL-%s-03' % (self.group.code, self.classifier.code), name='CLAVE ANTIGUA')
        session = self.session()
        session.workspace_add_products((product | legacy).ids)
        line, legacy_line = session.line_ids.sorted('id')
        self.assertTrue(line.preserve_reference and legacy_line.preserve_reference)
        self.assertEqual(line.reference, self.prefix + '-05')
        self.assertEqual(legacy_line.reference, legacy.default_code, 'la clave con el orden anterior se conserva tal cual')
        self.assertEqual(session.line_ids.mapped('consecutive'), [0, 0], 'no consume consecutivos')
        self.assertEqual(self.env['biotex.product.sequence']._next(self.prefix), 6)
        with self.assertRaisesRegex(UserError, 'se conservan'):
            session.workspace_update_line(line.id, {'new_name': 'OTRO NOMBRE', 'uom_id': line.uom_id.id})
        session.workspace_update_line(line.id, {'new_name': line.new_name, 'uom_id': line.uom_id.id, 'model': 'M-77', 'notes': 'nueva característica'})
        preview = session.workspace_confirmation_preview()
        self.assertEqual(preview['changes'], [], 'ninguna referencia cambia')
        session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(product.default_code, self.prefix + '-05')
        self.assertEqual(product.name, 'PRODUCTO YA CLASIFICADO')
        self.assertEqual(product.biotex_model, 'M-77')
        self.assertEqual(legacy.default_code, legacy_line.reference)
        self.assertEqual(line.applied_reference_before, line.applied_reference_after)

    def test_changing_classification_of_a_classified_product_still_generates_a_reviewed_key(self):
        product = self.classified_product(self.prefix + '-05')
        session = self.session(brand_id=self.other_brand.id)
        session.workspace_add_products(product.ids)
        line = session.line_ids
        self.assertFalse(line.preserve_reference)
        self.assertEqual(line.reference, session.class_code + '-01')
        self.assertEqual(session.workspace_confirmation_preview()['changes'][0]['before'], self.prefix + '-05')
        # si la sesión vuelve a la clasificación original, la identidad se conserva de nuevo
        session.write({'brand_id': self.brand.id})
        self.assertTrue(line.preserve_reference)
        self.assertEqual(line.reference, self.prefix + '-05')

    def test_moving_a_classified_product_is_flagged_when_adding_confirming_and_after_apply(self):
        product = self.classified_product(self.prefix + '-05', name='PRODUCTO CON OTRA CLAVE')
        plain = self.product()
        session = self.session(brand_id=self.other_brand.id)
        # al buscar: la fila trae la clave actual para que el asistente pida confirmación
        records = {r['id']: r for r in session.workspace_search_products('PRODUCTO CON OTRA CLAVE')['records']}
        self.assertEqual(records[product.id]['reclassify_from'], self.prefix + '-05')
        self.assertEqual(session._classified_elsewhere(plain), '', 'un producto sin clave no es reclasificación')
        # desde la lista de productos: no se agrega a ciegas, queda pendiente de confirmar en el asistente
        Session = self.env['biotex.classification.session'].with_user(self.operator)
        Session.search([('user_id', '=', self.operator.id), ('state', '=', 'draft'), ('id', '!=', session.id)]).unlink()
        (product | plain).with_user(self.operator).action_open_classifier()
        self.assertEqual(session.line_ids.product_id, plain, 'el producto con otra clave espera la aceptación del usuario')
        # aceptado: la línea avisa, la revisión final lo marca y al aplicar queda en rojo
        session.workspace_add_products(product.ids)
        line = session.line_ids.filtered(lambda l: l.product_id == product)
        self.assertEqual(line._workspace_line()['reclassify_from'], self.prefix + '-05')
        preview = session.workspace_confirmation_preview()
        change = next(c for c in preview['changes'] if c['id'] == product.id)
        self.assertTrue(change['reclassified'])
        self.assertEqual((change['before'], change['after']), (self.prefix + '-05', line.reference))
        session.workspace_confirm(expected_revision=preview['revision'])
        self.assertTrue(line.reclassified)
        self.assertFalse(session.line_ids.filtered(lambda l: l.product_id == plain).reclassified)
        self.assertEqual(product.default_code, line.reference)
        self.assertTrue(product.default_code.startswith(session.class_code + '-'))

    # ------------------------------------------------------------ bloqueo entre sesiones
    def test_product_in_a_draft_session_is_marked_and_cannot_join_another_session(self):
        product = self.product()
        first = self.session()
        first.workspace_add_products(product.ids)
        self.assertEqual(product.biotex_classification_status, 'classifying')
        self.assertEqual(product.biotex_classification_session_id, first)
        second = self.session(user=self.colleague)
        result = second.workspace_add_products(product.ids)
        self.assertFalse(second.line_ids)
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual(second.workspace_search_products('Flow fixture')['records'][0]['locked_by'], first.name)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env['biotex.classification.session.line'].with_user(self.colleague).create({'session_id': second.id, 'product_id': product.id})
        first.action_cancel()
        self.assertFalse(product.biotex_classification_status)
        self.assertFalse(product.biotex_classification_session_id)
        second.workspace_add_products(product.ids)
        self.assertEqual(product.biotex_classification_session_id, second)
        self.confirm(second)
        self.assertFalse(product.biotex_classification_status, 'confirmar libera la marca')

    # ------------------------------------------------------------ apertura desde la lista
    def test_list_action_reuses_the_last_active_session_and_opens_a_new_tab(self):
        Session = self.env['biotex.classification.session'].with_user(self.operator)
        Session.search([('user_id', '=', self.operator.id), ('state', '=', 'draft')]).unlink()
        products = self.product() | self.product()
        action = products.with_user(self.operator).action_open_classifier()
        self.assertEqual((action['type'], action['target']), ('ir.actions.act_url', 'new'))
        session = Session.search([('user_id', '=', self.operator.id), ('state', '=', 'draft')])
        self.assertEqual(len(session), 1, 'sin borrador previo se crea una sesión vacía')
        self.assertIn('/biotex_catalog/classification/open/%d' % session.id, action['url'])
        self.assertEqual(session.line_ids.product_id, products)
        self.assertFalse(session.class_code)
        self.assertEqual(session.line_ids.mapped('consecutive'), [0, 0], 'sin clasificación no se reserva nada')
        # al fijar la clasificación se reservan los consecutivos
        session.workspace_set_classification(session.id, {'group_id': self.group.id, 'family_id': self.family.id,
                                                          'classifier_id': self.classifier.id, 'brand_id': self.brand.id})
        self.assertEqual(sorted(session.line_ids.mapped('consecutive')), [1, 2])
        # una segunda selección se suma a la misma sesión, no crea otra
        more = self.product()
        action = more.with_user(self.operator).action_open_classifier()
        self.assertIn('/open/%d' % session.id, action['url'])
        self.assertEqual(len(Session.search([('user_id', '=', self.operator.id), ('state', '=', 'draft')])), 1)
        self.assertEqual(session.line_ids.product_id, products | more)
        self.assertEqual(session.line_ids.filtered(lambda l: l.product_id == more).consecutive, 3)
        # productos ya tomados por otra sesión: se omiten con aviso; si son todos, error
        colleague_session = self.session(user=self.colleague)
        blocked = self.product()
        colleague_session.workspace_add_products(blocked.ids)
        action = (blocked | self.product()).with_user(self.operator).action_open_classifier()
        self.assertIn('ya están en otra clasificación en curso', unquote(action['url']))
        self.assertNotIn(blocked, session.line_ids.product_id)
        with self.assertRaises(UserError), self.cr.savepoint():
            blocked.with_user(self.operator).action_open_classifier()
