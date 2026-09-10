"""Incremental import; production requires the operator's explicit source digest."""
import base64
import json
import re
from pathlib import Path

from odoo import Command
from odoo.exceptions import UserError

from .catalog_workbook import plan_rows, read_products, text, useful, value


def existing_products(env):
    products = env['product.template'].with_context(active_test=False).search([])
    return [{'id': p.id, 'code': p.default_code, 'legacy': p.biotex_legacy_code,
             'source': p.biotex_import_source,
             'variants': [{'code': v.default_code, 'barcode': v.barcode}
                          for v in p.with_context(active_test=False).product_variant_ids]}
            for p in products]


def import_products(env, filename, *, apply=False, production_source_sha256=None):
    if not env.su:
        raise UserError('Esta migración debe ejecutarla el operador del servidor.')
    params = env['ir.config_parameter'].sudo()
    environment = params.get_param('bioteczac.environment')
    if env.cr.dbname != 'bioteczac' or environment not in ('qa', 'production'):
        raise UserError('Entorno no autorizado para esta migración.')
    if environment == 'production' and not production_source_sha256:
        raise UserError('La migración a producción requiere la huella del archivo autorizado.')
    data = read_products(filename)
    if production_source_sha256 and data['sha256'] != production_source_sha256:
        raise UserError('El archivo no coincide con la fuente autorizada para producción.')
    env.cr.execute("SELECT pg_advisory_xact_lock(hashtext('bioteczac.catalog.incremental'))")
    if apply:
        # Prevent native UI edits/creates from invalidating the reviewed identity
        # set. The operator stops QA while applying; the transaction is atomic.
        env.cr.execute('LOCK TABLE product_template, product_product IN SHARE ROW EXCLUSIVE MODE')
    plan = plan_rows(data, existing_products(env))
    report = {'filename': data['filename'], 'sha256': data['sha256'],
              'sheets': data['sheet_counts'], 'rows': len(plan),
              'existing_rows': sum(item['status'] == 'existing' for item in plan),
              'existing_products': len({item['product_id'] for item in plan if item['status'] == 'existing'}),
              'new_products': sum(item['status'] == 'create' for item in plan),
              'stock_imported': False, 'existing_products_updated': 0, 'details': []}
    if not apply or not report['new_products']:
        return report
    archive = env['ir.attachment'].create({
        'name': data['filename'], 'type': 'binary',
        'datas': base64.b64encode(Path(filename).read_bytes()),
        'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'res_model': 'res.company', 'res_id': env.ref('base.main_company').id, 'public': False,
    })
    cache = {}

    def resolve(model, label, create_values=None):
        label = useful(label)
        if not label:
            return env[model]
        key = model, label.casefold()
        if key not in cache:
            found = env[model].with_context(active_test=False).search([('name', '=ilike', label)])
            if len(found) > 1:
                raise UserError('Varias coincidencias para %s: %s' % (model, label))
            if not found and create_values is not None:
                found = env[model].create(dict(create_values, name=label))
            cache[key] = found
        return cache[key]

    def country(label, notes):
        label = useful(label)
        if not label:
            return False
        iso = {'MEXICO': 'MX', 'CHINA': 'CN', 'USA': 'US', 'EUA': 'US', 'INDIA': 'IN',
               'PAISES BAJOS': 'NL', 'DINAMARCA': 'DK', 'ALEMANIA': 'DE', 'JAPON': 'JP',
               'ESPAÑA': 'ES', 'REPUBLICA CHECA': 'CZ', 'MALASIA': 'MY', 'CANADA': 'CA'}.get(label.upper())
        if not iso:
            notes.append('País de origen sin resolver; se conserva literalmente: ' + label)
            return False
        return env['res.country'].search([('code', '=', iso)], limit=1).id

    def brand(code, label, notes):
        code, label = useful(code), useful(label)
        if not code or not label:
            return False
        if not re.fullmatch(r'[A-Z0-9]{4}', code):
            notes.append('Código de marca pendiente: ' + code)
            return False
        found = env['biotex.brand'].with_context(active_test=False).search([('code', '=', code)])
        if not found:
            from ..models.biotex_brand import normalize_brand
            found = env['biotex.brand'].with_context(active_test=False).search([
                ('normalized_name', '=', normalize_brand(label))])
            if found and found.code != code:
                notes.append('La marca ya existe con otro código: %s / %s.' % (code, found.code))
                return False
        if not found:
            found = env['biotex.brand'].create({'name': label, 'code': code,
                                              'notes': 'Proporcionada en ' + data['filename']})
        return found.id

    def relations(model, raw, notes):
        found = env[model]
        unresolved = []
        for label in re.split(r'[,;]', useful(raw) or ''):
            if not useful(label):
                continue
            match = resolve(model, label)
            if match:
                found |= match
            else:
                unresolved.append(label.strip())
        if unresolved:
            notes.append('%s: valores conservados en origen sin equivalencia validada: %s.' %
                         ('Equipos' if model == 'biotex.equipment' else 'Especialidades', ', '.join(unresolved)))
        return found.ids

    for item in plan:
        row = item['row']
        detail = {'sheet': row['worksheet'], 'row': row['worksheet_row'], 'status': item['status']}
        if item['status'] == 'existing':
            detail['product_id'] = item['product_id']
            report['details'].append(detail)
            continue
        notes = []
        code = useful(value(row, 5)) or useful(value(row, 21))
        group_code, brand_code, family_code, classifier_code, consecutive = [text(value(row, i)) for i in range(5)]
        family = env['product.category']
        classifier = env['biotex.classifier']
        if group_code and family_code:
            family = env['product.category'].search([
                ('biotex_group_id.code', '=', group_code), ('biotex_code', '=', family_code)])
            if not family:
                notes.append('Familia/grupo sin equivalencia validada: %s-%s.' % (group_code, family_code))
        if family and classifier_code:
            classifier = family.biotex_classifier_ids.filtered(lambda c: c.code == classifier_code)
            if not classifier:
                notes.append('Clasificador %s no autorizado para %s; se conserva en el origen.' %
                             (classifier_code, family.biotex_composite))
        if any((group_code, family_code, classifier_code, brand_code)):
            expected = '-'.join((group_code, brand_code, family_code, classifier_code, consecutive.zfill(2)))
            if code != expected:
                notes.append('La clave escrita %s difiere de las columnas (%s). No se corrigió automáticamente.' %
                             (code, expected))
                classifier = env['biotex.classifier']
        else:
            notes.append('El bloque de clasificación nueva está vacío; se conserva la referencia anterior.')
        ui = useful(value(row, 8))
        unit = resolve('uom.uom', ui, {'rounding': 1.0}) if ui else env.ref('uom.product_uom_unit')
        if not ui:
            notes.append('Unidad indivisible no informada. La unidad técnica de Odoo no acredita una presentación validada.')
        package = resolve('biotex.package.type', value(row, 9), {})
        if not useful(value(row, 9)) or value(row, 10) is None:
            notes.append('Empaque o contenido no informado.')
        manufacturer = resolve('res.partner', value(row, 16), {'is_company': True, 'company_id': False})
        distributor = resolve('res.partner', value(row, 17),
                              {'is_company': True, 'company_id': False, 'supplier_rank': 1})
        values = {
            'name': useful(value(row, 6)) or useful(value(row, 23)),
            'biotex_name': useful(value(row, 6)), 'default_code': code,
            'type': 'consu', 'is_storable': True, 'company_id': False,
            # Odoo 19 permits an empty category; an absent/unknown family must
            # stay empty rather than being assigned a made-up classification.
            'categ_id': family.id,
            'biotex_classifier_id': classifier.id,
            'biotex_brand_id': brand(brand_code, value(row, 11), notes),
            'biotex_consecutive': int(consecutive) if consecutive.isdigit() else 0,
            'biotex_measure': useful(value(row, 7)), 'biotex_content': ui,
            'uom_id': unit.id, 'biotex_package_type_id': package.id,
            'biotex_package_qty': float(value(row, 10) or 0),
            'biotex_reference': useful(value(row, 12)), 'biotex_model': useful(value(row, 13)),
            'barcode': useful(value(row, 14)), 'biotex_country_id': country(value(row, 15), notes),
            'biotex_manufacturer_id': manufacturer.id, 'biotex_primary_distributor_id': distributor.id,
            'biotex_usage_notes': useful(value(row, 20)),
            # No legacy fallback from new classification or manufacturer codes.
            'biotex_legacy_code': useful(value(row, 21)), 'biotex_alt_code': useful(value(row, 22)),
            'description': useful(value(row, 23)), 'biotex_characteristics': useful(value(row, 37)),
            'biotex_equipment_ids': [Command.set(relations('biotex.equipment', value(row, 18), notes))],
            'biotex_specialty_ids': [Command.set(relations('biotex.specialty', value(row, 19), notes))],
            'list_price': 0.0, 'standard_price': 0.0,
            'taxes_id': [Command.clear()], 'supplier_taxes_id': [Command.clear()],
            'sale_ok': False, 'purchase_ok': False,
            'biotex_import_sha256': data['sha256'],
            'biotex_import_source': {'filename': data['filename'], 'worksheet': row['worksheet'],
                'columns': data['columns'][row['worksheet']], 'rows': [row],
                'stock_imported': False, 'source_attachment_id': archive.id},
        }
        for field, column in (('biotex_price_2', 29), ('biotex_wholesale_2', 30),
                              ('biotex_price_3', 31), ('biotex_wholesale_3', 32),
                              ('biotex_price_4', 33), ('biotex_wholesale_4', 34), ('weight', 36)):
            if value(row, column) not in (None, ''):
                values[field] = float(value(row, column))
        notes.append('Sin carga de existencias. Precios históricos solo como referencia; moneda, unidad y condiciones comerciales pendientes de validación.')
        values.update(biotex_import_status='review', biotex_import_review='\n'.join(notes))
        product = env['product.template'].with_context(mail_create_nosubscribe=True).create(values)
        detail.update(product_id=product.id, code=product.default_code, issues=notes)
        report['details'].append(detail)
    env['ir.attachment'].create({
        'name': 'resultado-catalogo-%s.json' % data['sha256'][:12],
        'type': 'binary', 'datas': base64.b64encode(json.dumps(report, ensure_ascii=False).encode()),
        'mimetype': 'application/json', 'res_model': 'res.company',
        'res_id': env.ref('base.main_company').id, 'public': False,
    })
    params.set_param('bioteczac.catalog_incremental.' + data['sha256'], json.dumps({
        k: v for k, v in report.items() if k != 'details'}, ensure_ascii=False))
    return report
