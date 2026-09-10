from odoo import Command
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install','-at_install')
class TestProductDetails(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.family=cls.env['product.category'].search([('biotex_level','=','family'),('biotex_classifier_ids','!=',False)],limit=1)
        cls.brand=cls.env['biotex.brand'].create({'name':'adjustments fixture brand','code':'AJUS'})
        cls.operator=new_test_user(cls.env(context={**cls.env.context,'no_reset_password':True}),login='catalog_adjustments_operator',groups='biotex_catalog.group_catalog_classifier')

    def product(self, **values):
        return self.env['product.template'].create({'name':'aguja de prueba','biotex_name':'aguja de prueba',
            'categ_id':self.family.id,'biotex_classifier_id':self.family.biotex_classifier_ids[0].id,
            'biotex_brand_id':self.brand.id,'is_storable':True,**values})

    def session(self,product):
        session=self.env['biotex.classification.session'].with_user(self.operator).create({
            'group_id':self.family.biotex_group_id.id,'family_id':self.family.id,
            'classifier_id':self.family.biotex_classifier_ids[0].id,'brand_id':self.brand.id})
        session.workspace_add_products(product.ids)
        return session

    def stock(self,product,qty):
        location=self.env['stock.warehouse'].search([('company_id','=',self.env.company.id)],limit=1).lot_stock_id
        Quant=self.env['stock.quant'].with_context(inventory_mode=True)
        quant=Quant.create({'product_id':product.product_variant_id.id,'location_id':location.id,'inventory_quantity':qty})
        quant.action_apply_inventory()
        return quant

    def test_measurements_complement_and_optional_alerts(self):
        p=self.product(default_code='TEST-DETAILS')
        self.family.biotex_photo_required=False
        self.assertNotIn('medidas',p.biotex_missing)
        self.family.biotex_measure_required=True
        self.assertIn('medidas',p.biotex_missing)
        p.with_user(self.operator).write({'biotex_measure_ids':[
            Command.create({'component':'aguja','measure_type':'largo','value':32,'unit':'mm'}),
            Command.create({'component':'aguja','measure_type':'calibre','value':21,'unit':'g'}),
            Command.create({'component':'cable','measure_type':'largo','value':150,'unit':'cm'})],
            'biotex_description_extra':'estéril','biotex_internal_notes':'uso interno'})
        self.assertNotIn('medidas',p.biotex_missing)
        self.assertEqual(len(p.biotex_measure_ids),3)
        p.action_use_structured_description()
        self.assertIn('AGUJA LARGO 32 MM',p.name)
        self.assertIn('CABLE LARGO 150 CM',p.name)
        self.assertTrue(p.name.endswith('ESTÉRIL'))
        self.assertNotIn('USO INTERNO',p.name)

    def test_invalid_measurements_are_rejected(self):
        p=self.product()
        with self.assertRaises(ValidationError),self.cr.savepoint():
            p.biotex_measure_ids=[Command.create({'component':'cable','measure_type':'largo','value':-1,'unit':'cm'})]

    def test_presentation_codes_reuse_product_and_convert_units(self):
        p=self.product()
        ids=p.product_variant_ids.ids
        p.with_user(self.operator)._biotex_set_presentations([
            {'name':'caja 20','quantity':20,'barcode':'AJUS-PACK20'},
            {'name':'caja 50','quantity':50,'barcode':'AJUS-PACK50'},
            {'name':'caja 100','quantity':100,'barcode':'AJUS-PACK100'}])
        self.assertEqual(p.product_variant_ids.ids,ids)
        self.assertEqual(sorted(p.biotex_presentation_ids.mapped('biotex_quantity')),[20,50,100])
        fifty=p.biotex_presentation_ids.filtered(lambda r:r.barcode=='AJUS-PACK50')
        self.assertEqual(fifty.uom_id._compute_quantity(2,p.uom_id),100)
        self.assertIn(p.id,[row[0] for row in self.env['product.template'].name_search('AJUS-PACK50')])
        self.assertIn(p.product_variant_id.id,[row[0] for row in self.env['product.product'].name_search('AJUS-PACK50')])
        p.with_user(self.operator).write({'biotex_presentation_ids':[Command.create({'uom_id':p.uom_id.id,'barcode':'AJUS-SINGLE'})]})
        self.assertIn('AJUS-SINGLE',p.product_variant_id.product_uom_ids.mapped('barcode'))

    def test_presentation_rows_carry_their_own_package_type(self):
        caja = self.env['biotex.package.type'].search([('name', '=ilike', 'caja')], limit=1) or self.env['biotex.package.type'].create({'name': 'Caja'})
        bolsa = self.env['biotex.package.type'].create({'name': 'Bolsa QA empaque'})
        p = self.product()
        p.with_user(self.operator)._biotex_set_presentations([
            {'package_type_id': caja.id, 'quantity': 12, 'barcode': 'AJUS-TYPE-CAJA12'},
            {'package_type_id': bolsa.id, 'quantity': 1, 'barcode': 'AJUS-TYPE-BOLSA'},
            {'name': 'estuche antiguo', 'quantity': 2, 'barcode': 'AJUS-TYPE-LEGACY'}])
        rows = {r.barcode: r for r in p.product_variant_id.product_uom_ids}
        self.assertEqual(rows['AJUS-TYPE-CAJA12'].uom_id.name, 'CAJA CON 12')
        self.assertEqual(rows['AJUS-TYPE-CAJA12'].biotex_package_type_id, caja)
        self.assertEqual(rows['AJUS-TYPE-BOLSA'].uom_id.name, 'BOLSA QA EMPAQUE')
        self.assertEqual(rows['AJUS-TYPE-LEGACY'].uom_id.name, 'ESTUCHE ANTIGUO')
        data = {row['barcode']: row for row in p._biotex_presentation_data()}
        self.assertEqual((data['AJUS-TYPE-CAJA12']['package_type_id'], data['AJUS-TYPE-CAJA12']['quantity']), (caja.id, 12))
        self.assertEqual(data['AJUS-TYPE-BOLSA']['package_type_id'], bolsa.id)
        self.assertFalse(data['AJUS-TYPE-LEGACY']['package_type_id'])
        with self.assertRaisesRegex(ValidationError, 'tipo de empaque'), self.cr.savepoint():
            p._biotex_set_presentations([{'package_type_id': False, 'name': '', 'quantity': 3, 'barcode': 'AJUS-TYPE-NONE'}])

    def test_barcode_collision_and_fractional_presentation_rejected(self):
        a,b=self.product(),self.product(barcode='AJUS-TAKEN')
        with self.assertRaises(ValidationError),self.cr.savepoint():
            a._biotex_set_presentations([{'name':'caja','quantity':20,'barcode':b.barcode}])
        with self.assertRaises(ValidationError),self.cr.savepoint():
            a._biotex_set_presentations([{'name':'media pieza','quantity':.5,'barcode':'AJUS-HALF'}])

    def test_session_uses_primary_brand_and_keeps_new_details(self):
        other=self.env['biotex.brand'].create({'name':'previous brand','code':'AJU2'})
        p=self.product(biotex_brand_id=other.id,biotex_reference='SHARED-REF',biotex_usage_notes='anterior')
        self.product(biotex_reference='SHARED-REF')
        session=self.session(p)
        session.workspace_update_line(session.line_ids.id,{'new_name':'nombre confirmado','base_name':'aguja',
            'brand_id':other.id,'manufacturer_ref':'SHARED-REF','usage_notes':'','internal_notes':'solo interno',
            'compatibility_notes':'monitor x','description_extra':'estéril',
            'measure_data':[{'component':'aguja','measure_type':'largo','value':30,'unit':'mm'}],
            'presentation_data':[{'name':'caja 20','quantity':20,'barcode':'AJUS-DRAFT20'}]})
        self.assertFalse(p.biotex_measure_ids)
        preview=session.workspace_confirmation_preview()
        session.workspace_confirm(expected_revision=preview['revision'])
        self.assertEqual(p.biotex_brand_id,self.brand)
        self.assertFalse(p.biotex_usage_notes)
        self.assertEqual(p.biotex_internal_notes,'SOLO INTERNO')
        self.assertEqual(p.biotex_compatibility_notes,'MONITOR X')
        self.assertEqual(p.biotex_measure_ids.value,30)
        self.assertEqual(p.biotex_presentation_ids.barcode,'AJUS-DRAFT20')

    def test_stock_unit_is_not_reinterpreted(self):
        p=self.product()
        q=self.stock(p,12)
        other=self.env['uom.uom'].create({'name':'CAJA DE PRUEBA','relative_uom_id':p.uom_id.id,'relative_factor':20})
        with self.assertRaisesRegex(UserError,'movimientos'):
            p.write({'uom_id':other.id})
        self.assertEqual(q.quantity,12)

    def test_old_codes_remain_searchable_and_cannot_be_reused(self):
        p=self.product()
        p.action_assign_clave()
        old=p.default_code
        p.write({'default_code':p._biotex_clave_prefix()+'99','barcode':p._biotex_clave_prefix()+'99','biotex_consecutive':99})
        self.assertIn(old,p.biotex_code_history_ids.mapped('code'))
        self.assertIn(old,p.biotex_presentation_ids.mapped('barcode'))
        self.assertIn(p.id,[row[0] for row in self.env['product.template'].name_search(old)])
        with self.assertRaisesRegex(ValidationError,'historial'),self.cr.savepoint():
            self.product(default_code=old)

    def test_reorder_by_component_converts_length_and_preserves_ids(self):
        a=self.product(name='a producto',biotex_measure_ids=[Command.create({'component':'aguja','measure_type':'largo','value':2,'unit':'cm'})])
        b=self.product(name='z producto',biotex_measure_ids=[Command.create({'component':'aguja','measure_type':'largo','value':15,'unit':'mm'})])
        (a|b).action_assign_clave()
        old=a.default_code
        identities=(a|b).product_variant_ids.ids
        wizard=self.env['biotex.reorder.wizard'].with_user(self.env.ref('base.user_admin')).create({'product_ids':[Command.set((a|b).ids)],'component':'AGUJA','measure_type':'LARGO'})
        wizard.action_apply()
        self.assertLess(b.biotex_consecutive,a.biotex_consecutive)
        self.assertEqual((a|b).product_variant_ids.ids,identities)
        self.assertIn(old,a.biotex_code_history_ids.mapped('code'))
        history=self.env['biotex.reorder.wizard'].create({'historical_prefix':a._biotex_clave_prefix()})
        self.assertTrue(history._groups())

    def test_auxiliary_duplicates_are_normalized_and_catalogs_expand(self):
        self.env['biotex.specialty'].create({'name':'área clínica de prueba','code':'AJP'})
        with self.assertRaises(ValidationError),self.cr.savepoint():
            self.env['biotex.specialty'].create({'name':'AREA   CLINICA DE PRUEBA','code':'AJQ'})
        self.env['biotex.classifier'].create({'name':'clasificador único prueba','code':'AJP','group_id':self.family.biotex_group_id.id})
        with self.assertRaises(ValidationError),self.cr.savepoint():
            self.env['biotex.classifier'].create({'name':'CLASIFICADOR UNICO PRUEBA','code':'AJQ','group_id':self.family.biotex_group_id.id})
        Session=self.env['biotex.classification.session'].with_user(self.operator)
        maker=Session.workspace_create_relation('manufacturer','nuevo fabricante de prueba')
        distributor=Session.workspace_create_relation('distributor','nuevo distribuidor de prueba')
        self.assertEqual(maker['name'],'NUEVO FABRICANTE DE PRUEBA')
        self.assertTrue(self.env['res.partner'].browse(maker['id']).biotex_is_manufacturer)
        self.assertTrue(self.env['res.partner'].browse(distributor['id']).supplier_rank)
        self.assertEqual(Session.workspace_create_relation('manufacturer','NUEVO FABRICANTE DE PRUEBA')['id'],maker['id'])
        with self.assertRaises(UserError):Session.workspace_create_relation('arbitrary_field','X')

    def test_merge_preserves_stock_and_barcodes_and_archives_sources(self):
        target=self.product(default_code='AJUS-MERGE-A',barcode='AJUS-MAIN-A')
        source=self.product(default_code='AJUS-MERGE-B',barcode='AJUS-MAIN-B')
        source._biotex_set_presentations([{'name':'caja 50','quantity':50,'barcode':'AJUS-MERGE-PACK50'}])
        package_unit=source.biotex_presentation_ids.uom_id
        self.stock(target,5)
        self.stock(source,7)
        wizard=self.env['biotex.product.merge.wizard'].create({'product_ids':[Command.set((target|source).ids)],'target_id':target.id})
        wizard.action_merge()
        self.assertFalse(source.active)
        self.assertEqual(source.biotex_merged_into_id,target)
        self.assertEqual(target.qty_available,12)
        self.assertEqual(source.with_context(active_test=False).qty_available,0)
        self.assertIn('AJUS-MAIN-B',target.biotex_presentation_ids.mapped('barcode'))
        self.assertIn('AJUS-MERGE-B',target.biotex_code_history_ids.mapped('code'))
        self.assertIn(package_unit,target.uom_ids)
        self.assertIn('AJUS-MERGE-PACK50',target.biotex_presentation_ids.mapped('barcode'))

    def test_merge_rejects_reservations_and_classifier_permission(self):
        target,source=self.product(),self.product()
        quant=self.stock(source,7)
        quant.reserved_quantity=1
        wizard=self.env['biotex.product.merge.wizard'].create({'product_ids':[Command.set((target|source).ids)],'target_id':target.id})
        with self.assertRaisesRegex(UserError,'reservas'):wizard.action_merge()
        with self.assertRaises(AccessError):wizard.with_user(self.operator).read(['target_id'])
