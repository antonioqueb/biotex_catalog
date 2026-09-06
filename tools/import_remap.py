"""Transactional, repeat-safe import into existing catalog models. No demo generator."""
import base64
import json
from collections import defaultdict

from odoo import Command
from odoo.exceptions import UserError
from .remap_workbook import read_workbook, SHEETS

STATUS = {'ACTIVA': 'active', 'PENDIENTE': 'pending', 'PROPUESTA': 'proposed'}


def import_catalog(env, filename, operational_prices=False):
    data = read_workbook(filename)
    params = env['ir.config_parameter'].sudo()
    previous = params.get_param('bioteczac.catalog_source_sha256')
    if previous:
        if previous != data['sha256']:
            raise UserError('La base ya tiene otra migración de catálogo; se requiere revisión explícita.')
        products = env['product.template'].with_context(active_test=False).search([('biotex_import_sha256', '=', previous)])
        if len(products) != data['summary']['unique_products']:
            raise UserError('El catálogo importado cambió; no se recrearán fichas automáticamente.')
        return dict(data['summary'], sha256=previous, repeated=True)
    if env['product.template'].with_context(active_test=False).search_count([('biotex_group_id', '!=', False)]):
        raise UserError('Este importador de arranque necesita un catálogo clasificado vacío.')

    def record(model, key, values):
        xmlid = 'biotex_catalog.xlsx_v2_' + key.lower().replace('-', '_')
        result = env.ref(xmlid, raise_if_not_found=False)
        if result:
            raise UserError('Existe un registro de una migración incompleta: ' + xmlid)
        result = env[model].with_context(tracking_disable=True, mail_create_nosubscribe=True).create(values)
        module, name = xmlid.split('.', 1)
        env['ir.model.data'].create({'module': module, 'name': name, 'model': model,
                                     'res_id': result.id, 'noupdate': True})
        return result

    divisions = {r[0]: record('biotex.division', 'division_' + r[0], {
        'code': r[0], 'name': r[1], 'accounting_nature': r[2], 'inventory_policy': r[3],
    }) for r in data['divisions']}
    groups = {r[0]: record('biotex.group', 'group_' + r[0], {
        'code': r[0], 'name': r[1], 'division_id': divisions[r[2]].id,
        'regulated': r[3] == 'SI', 'classifier_axis': r[4], 'note': r[5] or False,
    }) for r in data['groups']}
    classifiers = {(r[1], r[2]): record('biotex.classifier', 'classifier_' + r[3], {
        'code': r[2], 'name': r[4], 'group_id': groups[r[1]].id, 'status': STATUS[r[6]],
    }) for r in data['classifiers']}
    bridges = defaultdict(list)
    for r in data['family_classifiers']:
        if r[5] == 'SI':
            bridges[(r[1], r[2])].append(classifiers[(r[1], r[3])].id)
    families = {(r[1], r[2]): record('product.category', 'family_' + r[3], {
        'name': r[4], 'biotex_group_id': groups[r[1]].id, 'biotex_code': r[2],
        'biotex_status': STATUS[r[5]], 'biotex_origin': r[6],
        'biotex_classifier_ids': [Command.set(bridges[(r[1], r[2])])],
        'biotex_photo_required': False,
    }) for r in data['families']}
    brands = {r[0]: record('biotex.brand', 'brand_' + r[0], {
        'name': r[1], 'code': r[0], 'notes': r[2],
    }) for r in data['brands']}
    specialties = {r[0]: record('biotex.specialty', 'specialty_' + r[0], {'code': r[0], 'name': r[1]})
                   for r in data['specialties']}
    equipment = {r[0]: record('biotex.equipment', 'equipment_' + r[0], {'code': r[0], 'name': r[1]})
                 for r in data['equipment']}
    for r in data['subclasses']:
        record('biotex.mt.subclass', 'subclass_' + r[0] + '_' + r[1], {
            'family_id': families[('MT', r[0])].id, 'code': r[1], 'name': r[2],
        })
    # Every worksheet is retained as values AND original formulas, with exact source columns.
    archive = record('ir.attachment', 'source_workbook', {
        'name': data['filename'], 'type': 'binary', 'datas': base64.b64encode(open(filename, 'rb').read()),
        'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'res_model': 'res.company', 'res_id': env.ref('base.main_company').id, 'public': False,
    })
    import openpyxl
    original = openpyxl.load_workbook(filename, read_only=True, data_only=False)
    evaluated = openpyxl.load_workbook(filename, read_only=True, data_only=True)
    all_sheets = {sheet.title: {'values': list(evaluated[sheet.title].values), 'formulas': list(sheet.values)} for sheet in original}
    record('ir.attachment', 'source_all_sheets', {
        'name': 'catalogo-v2-todas-las-hojas.json', 'type': 'binary',
        'datas': base64.b64encode(json.dumps(all_sheets, ensure_ascii=False, default=str).encode()),
        'mimetype': 'application/json', 'res_model': 'res.company',
        'res_id': env.ref('base.main_company').id, 'public': False,
    })
    original.close(); evaluated.close()
    contacts, units, packages, generics = {}, {}, {}, {}
    special_bridge, equipment_bridge = defaultdict(list), defaultdict(list)
    for r in data['product_specialties']: special_bridge[r[0]].append(r)
    for r in data['product_equipment']: equipment_bridge[r[0]].append(r)

    def text(value):
        return str(value).strip() if value is not None else ''

    def useful(value):
        value = text(value)
        return value if value.upper() not in ('', 'N/A', 'N/D', 'NA') else False

    def contact(value, supplier=False):
        name = useful(value)
        if not name: return False
        if name not in contacts:
            contacts[name] = env['res.partner'].with_context(tracking_disable=True).create({
                'name': name, 'is_company': True, 'company_id': False,
                'supplier_rank': 1 if supplier else 0,
                'comment': 'Nombre proporcionado en el catálogo XLSX. Datos fiscales y comerciales pendientes de validación.',
            })
        if supplier and not contacts[name].supplier_rank: contacts[name].supplier_rank = 1
        return contacts[name].id

    def unit(value):
        name = useful(value)
        if not name: return env.ref('uom.product_uom_unit')
        if name not in units:
            values = {'name': name, 'rounding': 1.0}
            if 'category_id' in env['uom.uom']._fields:
                values.update(category_id=env['uom.category'].create({'name': 'Presentación ' + name}).id,
                              uom_type='reference', factor=1.0)
            # In Odoo 19 no relative unit is assigned: no invented box/piece conversion.
            units[name] = env['uom.uom'].create(values)
        return units[name]

    def package(value):
        name = useful(value)
        if not name: return False
        if name not in packages:
            packages[name] = env['biotex.package.type'].create({'name': name})
        return packages[name].id

    review_count = 0
    for index, (key, source_rows) in enumerate(data['products'].items(), 1):
        v = source_rows[0]['values']
        family, classifier = families[(v[58], v[59])], classifiers[(v[58], v[60])]
        if v[64] not in generics:
            generics[v[64]] = record('biotex.generic', 'generic_' + v[64], {
                'code': v[64], 'name': v[6], 'family_id': family.id, 'classifier_id': classifier.id,
                'measure': v[7] or False, 'consecutive': int(v[64].rsplit('-', 1)[1]),
            })
        incidents = [r for r in data['incidents'] if r[0] in [x['values'][56] for x in source_rows] or r[1] == key]
        notes = []
        if len(source_rows) > 1:
            notes.append('Clave repetida en %s renglones. Se conserva cada variante de referencia, descripción y precio; validar una ficha antes de operar.' % len(source_rows))
        if not useful(v[8]): notes.append('Unidad indivisible no indicada; debe validarse antes de comprar o vender.')
        if not useful(v[9]) or v[10] is None: notes.append('Empaque o contenido pendiente de validar.')
        reference_prices = not operational_prices or len(source_rows) > 1
        if reference_prices: notes.append('Precios históricos conservados en los renglones de origen; moneda y base de presentación pendientes de validación.')
        if incidents: notes.append('Incidencias originales: ' + ' | '.join(text(r[4]) for r in incidents))
        pending = len(source_rows) > 1 or not useful(v[8]) or not useful(v[9]) or v[10] is None
        review_count += int(pending)
        country_code = {'USA':'US', 'INDIA':'IN', 'PAISES BAJOS':'NL', 'MEXICO':'MX',
                        'DINAMARCA':'DK', 'ALEMANIA':'DE', 'JAPON':'JP', 'CHINA':'CN', 'ESPAÑA':'ES',
                        'REPUBLICA CHECA':'CZ', 'MALASIA':'MY', 'CANADA':'CA', 'EUA':'US'}.get(text(v[15]).upper())
        country = env['res.country'].search([('code', '=', country_code)], limit=1) if country_code else env['res.country']
        values = {
            'name': v[6], 'biotex_name': v[6], 'default_code': key, 'type': 'consu', 'is_storable': True,
            'company_id': False, 'categ_id': family.id, 'biotex_classifier_id': classifier.id,
            'biotex_brand_id': brands[v[61]].id, 'biotex_consecutive': int(v[62]),
            'biotex_generic_id': generics[v[64]].id, 'biotex_measure': v[7] or False,
            'biotex_content': v[8] or False, 'uom_id': unit(v[8]).id,
            'biotex_package_type_id': package(v[9]), 'biotex_package_qty': float(v[10] or 0),
            'biotex_reference': useful(v[12]), 'biotex_model': useful(v[13]), 'barcode': useful(v[14]),
            'biotex_country_id': country.id, 'biotex_manufacturer_id': contact(v[16]),
            'biotex_primary_distributor_id': contact(v[17], supplier=True),
            'biotex_usage_notes': v[20] or False, 'biotex_legacy_code': useful(v[21]),
            'biotex_alt_code': useful(v[22]), 'description': v[23] or False,
            'biotex_characteristics': v[37] or False,
            'list_price': 0.0 if reference_prices else float(v[28] or 0),
            'standard_price': 0.0, 'taxes_id': [Command.clear()], 'supplier_taxes_id': [Command.clear()],
            'biotex_price_2': float(v[29] or 0), 'biotex_wholesale_2': float(v[30] or 0),
            'biotex_price_3': float(v[31] or 0), 'biotex_wholesale_3': float(v[32] or 0),
            'biotex_price_4': float(v[33] or 0), 'biotex_wholesale_4': float(v[34] or 0),
            'biotex_specialty_ids': [Command.set(list({specialties[r[1]].id for r in special_bridge[key]}))],
            'biotex_equipment_ids': [Command.set(list({equipment[r[1]].id for r in equipment_bridge[key]}))],
            'biotex_main_specialty_id': next((specialties[r[1]].id for r in special_bridge[key] if r[2] == 'S'), False),
            'biotex_main_equipment_id': next((equipment[r[1]].id for r in equipment_bridge[key] if r[2] == 'S'), False),
            'biotex_import_sha256': data['sha256'],
            'biotex_import_source': {'columns': data['headers'], 'rows': source_rows, 'incidents': incidents,
                                    'specialties': special_bridge[key], 'equipment': equipment_bridge[key],
                                    'source_attachment_id': archive.id},
            'biotex_import_review': '\n'.join(notes),
            'biotex_import_status': 'review' if pending else 'reference',
            'sale_ok': not pending and not reference_prices, 'purchase_ok': not pending and not reference_prices,
            'image_1920': False, 'biotex_image_2': False, 'biotex_image_3': False,
        }
        record('product.template', 'product_' + key, values)
    params.set_param('bioteczac.catalog_source_sha256', data['sha256'])
    result = dict(data['summary'], sha256=data['sha256'], review_products=review_count,
                  source_contacts=len(contacts), source_units=len(units), source_packages=len(packages),
                  all_worksheets=len(all_sheets), operational_prices=operational_prices)
    params.set_param('bioteczac.catalog_import_report', json.dumps(result, sort_keys=True))
    return result
