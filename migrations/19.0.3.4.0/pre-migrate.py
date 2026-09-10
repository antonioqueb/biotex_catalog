"""Tipos de empaque: los registros creados por el importador se enlazan a los identificadores del catálogo.

El archivo data/package_type_data.xml no se cargaba; al activarlo, cada tipo ya existente con el mismo nombre
(sin distinguir mayúsculas) toma el identificador externo correspondiente para que la carga no lo duplique.
"""
PACKAGE_TYPES = {
    'package_type_pieza': 'PIEZA', 'package_type_sobre': 'SOBRE', 'package_type_caja': 'CAJA', 'package_type_bolsa': 'BOLSA',
    'package_type_paquete': 'PAQUETE', 'package_type_frasco': 'FRASCO', 'package_type_tubo': 'TUBO', 'package_type_ampolleta': 'AMPOLLETA',
    'package_type_juego': 'JUEGO', 'package_type_unidad': 'UNIDAD', 'package_type_otro': 'OTRO',
}


def migrate(cr, version):
    for xmlid, name in PACKAGE_TYPES.items():
        cr.execute("SELECT 1 FROM ir_model_data WHERE module = 'biotex_catalog' AND name = %s", (xmlid,))
        if cr.fetchone():
            continue
        cr.execute("SELECT id FROM biotex_package_type WHERE upper(name) = %s ORDER BY id LIMIT 1", (name,))
        row = cr.fetchone()
        if row:
            cr.execute("""INSERT INTO ir_model_data (module, name, model, res_id, noupdate, create_date, write_date)
                          VALUES ('biotex_catalog', %s, 'biotex.package.type', %s, true, now(), now())""", (xmlid, row[0]))
