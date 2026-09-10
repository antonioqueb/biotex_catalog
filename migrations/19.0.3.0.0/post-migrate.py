from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env=api.Environment(cr,SUPERUSER_ID,{'active_test':False,'tracking_disable':True,'mail_create_nosubscribe':True})
    products=env['product.template'].search([])
    manufacturers=products.biotex_manufacturer_id
    distributors=products.biotex_primary_distributor_id
    manufacturers.write({'biotex_is_manufacturer':True})
    distributors.write({'biotex_is_primary_distributor':True})
    for row in manufacturers | distributors:
        if row.name and row.name!=row.name.strip().upper():row.name=row.name.strip().upper()
    for model in ('biotex.specialty','biotex.classifier','biotex.brand'):
        for row in env[model].search([]):
            if row.name and row.name!=row.name.strip().upper():row.name=row.name.strip().upper()
    # Original workbooks/provenance and operational quantities remain unchanged.
    for product in products:
        changes={field:product[field].strip().upper() for field in product._UPPER_FIELDS
                 if product[field] and product[field] != product[field].strip().upper()}
        if changes:product.write(changes)
    History=env['biotex.product.code.history']
    for line in env['biotex.classification.session.line'].search([]):
        for code in {line.old_reference,line.applied_reference_before,line.applied_reference_after}-{False,''}:
            if code!=line.product_id.default_code:History._remember(line.product_id,code,'HISTORIAL DE CLASIFICACIÓN ANTERIOR')
    for product in products:
        if product.biotex_legacy_code and product.biotex_legacy_code!=product.default_code:
            History._remember(product,product.biotex_legacy_code,'CLAVE DEL CATÁLOGO DE ORIGEN')
