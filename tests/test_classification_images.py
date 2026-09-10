import base64
from io import BytesIO

from PIL import Image
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


def photo(color):
    stream = BytesIO()
    Image.new('RGB', (24, 24), color).save(stream, format='PNG')
    return base64.b64encode(stream.getvalue()).decode()


@tagged('post_install', '-at_install')
class TestClassificationImages(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.family = cls.env['product.category'].search([('biotex_level', '=', 'family'), ('biotex_classifier_ids', '!=', False)], limit=1)
        cls.brand = cls.env['biotex.brand'].create({'name': 'QA imágenes de clasificación', 'code': 'IMAG'})
        cls.operator = new_test_user(cls.env(context={**cls.env.context, 'no_reset_password': True}), login='qa_classification_images', groups='biotex_catalog.group_catalog_classifier')

    def setUp(self):
        super().setUp()
        self.product = self.env['product.template'].create({'name': 'QA producto con imágenes', 'image_1920': photo('red')})
        self.session = self.env['biotex.classification.session'].with_user(self.operator).create({
            'group_id': self.family.biotex_group_id.id, 'family_id': self.family.id,
            'classifier_id': self.family.biotex_classifier_ids[:1].id, 'brand_id': self.brand.id})
        self.session.workspace_add_products(self.product.ids)
        self.line = self.session.line_ids

    def save_photo(self, **changes):
        return self.session.workspace_update_line(self.line.id, {'image_changes': changes})

    def confirm(self):
        preview = self.session.workspace_confirmation_preview()
        self.session.workspace_confirm(expected_revision=preview['revision'])

    def test_view_save_reopen_and_apply_photos_with_classification(self):
        before = self.product.image_1920
        photos = self.session.workspace_line_detail(self.line.id)['line']['photos']
        self.assertEqual(len(photos), 3)
        self.assertIn('/product.template/', photos[0]['url'])
        self.assertFalse(photos[1]['url'])
        self.save_photo(biotex_image_2=photo('blue'))
        self.assertEqual(self.product.image_1920, before)
        self.assertFalse(self.product.biotex_image_2)
        reopened = self.session.workspace_line_detail(self.line.id)['line']['photos'][1]
        self.assertTrue(reopened['pending'])
        self.assertIn('/biotex.classification.session.line/', reopened['url'])
        self.confirm()
        self.assertEqual(self.product.biotex_image_2, self.line.biotex_image_2)
        self.assertEqual(self.product.image_1920, before)
        self.assertEqual(self.product.biotex_photo_count, 2)
        if 'biotex.catalog.image.event' in self.env:
            events = self.env['biotex.catalog.image.event'].sudo().search([('product_id', '=', self.product.id), ('image_field', '=', 'biotex_image_2'), ('kind', '=', 'upload')])
            self.assertEqual(len(events), 1)
            self.assertEqual(events.user_id, self.operator)
        with self.assertRaises(UserError):
            self.save_photo(biotex_image_3=photo('green'))

    def line_images(self):
        session = self.session.workspace_bootstrap(self.session.id)['session']
        return next(line for line in session['lines'] if line['id'] == self.line.id)['images']

    def test_step3_image_column_payload_comes_with_the_lines(self):
        images = self.line_images()
        self.assertEqual([(i['label'], i['pending']) for i in images], [('Principal', False)])
        self.assertIn('/web/image/product.template/%d/image_1920?' % self.product.id, images[0]['url'])
        self.assertIn('width=96', images[0]['thumb_url'])
        self.save_photo(biotex_image_3=photo('blue'))
        images = self.line_images()
        self.assertEqual([(i['label'], i['pending']) for i in images], [('Principal', False), ('Secundaria 2', True)])
        self.assertIn('/biotex.classification.session.line/%d/biotex_image_3?' % self.line.id, images[1]['url'])
        self.product.biotex_image_2 = photo('green')
        self.assertEqual([i['field'] for i in self.line_images()], ['image_1920', 'biotex_image_2', 'biotex_image_3'])
        self.assertLessEqual(len(self.line_images()), 3)
        empty = self.env['product.template'].create({'name': 'QA producto sin imagen'})
        self.session.workspace_add_products(empty.ids)
        session = self.session.workspace_bootstrap(self.session.id)['session']
        self.assertEqual(next(l for l in session['lines'] if l['product_id'] == empty.id)['images'], [])

    def test_discard_pending_photo_and_preserve_other_live_uploads(self):
        before = self.product.image_1920
        self.save_photo(image_1920=photo('blue'), biotex_image_2=photo('green'))
        self.save_photo(image_1920=False)
        self.product.biotex_image_3 = photo('yellow')
        other = self.product.biotex_image_3
        self.confirm()
        self.assertEqual(self.product.image_1920, before)
        self.assertEqual(self.product.biotex_image_3, other)
        self.assertTrue(self.product.biotex_image_2)

    def test_reject_overwriting_a_photo_changed_after_draft_save(self):
        self.save_photo(image_1920=photo('blue'))
        self.product.image_1920 = photo('green')
        current = self.product.image_1920
        self.assertTrue(self.line._workspace_detail()['photos'][0]['conflict'])
        with self.assertRaisesRegex(UserError, 'cambió en el catálogo'), self.cr.savepoint():
            self.confirm()
        self.assertEqual(self.product.image_1920, current)
        self.save_photo(image_1920=False)
        self.confirm()
        self.assertEqual(self.product.image_1920, current)

    def test_invalid_files_are_atomic_and_image_metadata_is_protected(self):
        before = self.line.new_name
        with self.assertRaises(UserError), self.cr.savepoint():
            self.session.workspace_update_line(self.line.id, {'new_name': 'NO GUARDAR', 'image_changes': {'image_1920': base64.b64encode(b'not an image').decode()}})
        self.assertEqual(self.line.new_name, before)
        with self.assertRaises(UserError):
            self.save_photo(image_1920='invalid base64')
        with self.assertRaises(UserError):
            self.save_photo(other_field=photo('red'))
        with self.assertRaises(UserError):
            self.line.write({'image_1920': photo('red'), 'photo_baselines': {}})
