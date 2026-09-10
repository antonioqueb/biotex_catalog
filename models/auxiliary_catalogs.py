from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from .product_details import upper, normalized


class Specialty(models.Model):
    _inherit='biotex.specialty'
    normalized_name=fields.Char(compute='_compute_normalized_name',store=True,index=True)
    _normalized_name_unique=models.Constraint('unique(normalized_name)','La especialidad ya existe; utilice el registro existente.')

    @api.depends('name')
    def _compute_normalized_name(self):
        for row in self:row.normalized_name=normalized(row.name)

    @api.constrains('name')
    def _check_normalized_duplicate(self):
        for row in self:
            if self.sudo().with_context(active_test=False).search_count([('normalized_name','=',normalized(row.name)),('id','!=',row.id)],limit=1):
                raise ValidationError('La especialidad ya existe; utilice el registro existente.')

    @api.model_create_multi
    def create(self, vals_list):
        seen=set()
        for vals in vals_list:
            key=normalized(vals.get('name'))
            if key in seen or self.sudo().with_context(active_test=False).search_count([('normalized_name','=',key)],limit=1):
                raise ValidationError('La especialidad ya existe; utilice el registro existente.')
            seen.add(key)
        return super().create([{**v,'name':upper(v.get('name'))} for v in vals_list])

    def write(self, vals):
        if 'name' in vals and (len(self)>1 or self.sudo().with_context(active_test=False).search_count([('normalized_name','=',normalized(vals['name'])),('id','not in',self.ids)],limit=1)):
            raise ValidationError('La especialidad ya existe; utilice el registro existente.')
        return super().write({**vals,**({'name':upper(vals['name'])} if 'name' in vals else {})})


class Classifier(models.Model):
    _inherit='biotex.classifier'
    normalized_name=fields.Char(compute='_compute_normalized_name',store=True,index=True)
    _normalized_group_unique=models.Constraint('unique(group_id,normalized_name)','Ya existe esa clasificación en el grupo; utilice la existente.')

    @api.depends('name')
    def _compute_normalized_name(self):
        for row in self:row.normalized_name=normalized(row.name)

    @api.constrains('name','group_id')
    def _check_normalized_duplicate(self):
        for row in self:
            if self.sudo().with_context(active_test=False).search_count([('group_id','=',row.group_id.id),('normalized_name','=',normalized(row.name)),('id','!=',row.id)],limit=1):
                raise ValidationError('Ya existe esa clasificación en el grupo; utilice la existente.')

    @api.model_create_multi
    def create(self, vals_list):
        seen=set()
        for vals in vals_list:
            key=(vals.get('group_id'),normalized(vals.get('name')))
            if key in seen or self.sudo().with_context(active_test=False).search_count([('group_id','=',key[0]),('normalized_name','=',key[1])],limit=1):
                raise ValidationError('Ya existe esa clasificación en el grupo; utilice la existente.')
            seen.add(key)
        return super().create([{**v,'name':upper(v.get('name'))} for v in vals_list])

    def write(self, vals):
        if {'name','group_id'} & set(vals):
            for row in self:
                if self.sudo().with_context(active_test=False).search_count([('group_id','=',vals.get('group_id',row.group_id.id)),('normalized_name','=',normalized(vals.get('name',row.name))),('id','!=',row.id)],limit=1):
                    raise ValidationError('Ya existe esa clasificación en el grupo; utilice la existente.')
        return super().write({**vals,**({'name':upper(vals['name'])} if 'name' in vals else {})})


class CatalogPartner(models.Model):
    _inherit='res.partner'
    biotex_is_manufacturer=fields.Boolean(string='Fabricante de insumos',index=True)
    biotex_is_primary_distributor=fields.Boolean(string='Distribuidor primario de insumos',index=True)

    @api.model_create_multi
    def create(self, vals_list):
        prepared=[]
        for vals in vals_list:
            vals=dict(vals)
            if vals.get('biotex_is_manufacturer') or vals.get('biotex_is_primary_distributor'):
                if 'name' in vals:vals['name']=upper(vals['name'])
                vals['is_company']=True
            if vals.get('biotex_is_primary_distributor'):
                vals['supplier_rank']=max(vals.get('supplier_rank',0),1)
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if 'name' in vals and (vals.get('biotex_is_manufacturer') or vals.get('biotex_is_primary_distributor') or
                              any(p.biotex_is_manufacturer or p.biotex_is_primary_distributor for p in self)):
            vals={**vals,'name':upper(vals['name'])}
        return super().write(vals)


class CatalogBrand(models.Model):
    _inherit='biotex.brand'

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([{**v,**{k:upper(v[k]) for k in ('name','code') if k in v}} for v in vals_list])

    def write(self, vals):
        return super().write({**vals,**{k:upper(vals[k]) for k in ('name','code') if k in vals}})


class Family(models.Model):
    _inherit='product.category'
    biotex_measure_required=fields.Boolean(string='Medidas obligatorias',default=False,
        help='Actívelo únicamente en familias que necesiten medidas para completar la clasificación.')


class SessionRelations(models.Model):
    _inherit='biotex.classification.session'

    @api.model
    def workspace_create_relation(self, kind, name):
        if not (self.env.su or self.env.user.has_group('biotex_catalog.group_catalog_classifier') or self.env.user.has_group('biotex_base.group_biotex_direction')):
            raise UserError('Se requiere acceso al clasificador.')
        field={'manufacturer':'biotex_is_manufacturer','distributor':'biotex_is_primary_distributor'}.get(kind)
        name=upper(name or '')
        if not field or not name:
            raise UserError('Indique el nombre del fabricante o distribuidor.')
        Partner=self.env['res.partner']
        matches=Partner.search([('is_company','=',True),('name','=ilike',name)])
        if len(matches)>1:
            raise UserError('Hay varios contactos con ese nombre; seleccione uno en el catálogo.')
        if matches:
            # Only tag a contact already visible to this operator. Do not grant
            # general contact editing to the catalog classifier role.
            matches.sudo().write({field:True,**({'supplier_rank':max(matches.supplier_rank,1)} if kind=='distributor' else {})})
            record=matches
        else:
            record=Partner.sudo().create({'name':name,'is_company':True,field:True})
        return {'id':record.id,'name':record.display_name}
