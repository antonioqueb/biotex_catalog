# Reinicio autorizado de un prefijo

El contador conserva su política normal de no reutilizar claves. Excepcionalmente,
un operador con autorización puede registrar un corte para un prefijo en
`ir.config_parameter`, clave `biotex_catalog.sequence_reset_boundary.<PREFIX>`.
El valor JSON contiene los máximos IDs de `biotex.product.code.history` y
`biotex.classification.session.line` en `history_id` y `line_id`, además de fecha,
motivo y referencia de evidencia. No hay acción pública ni cambio de ACL.

Antes del corte se respaldan los datos, se bloquean escrituras concurrentes y se
resuelven los borradores afectados. Se comprueban las claves vigentes, incluidas
las archivadas, y se alinean los metadatos del producto con su código válido.
Finalmente se registra el corte y se escribe el contador en la misma transacción.
El corte nunca se debe crear automáticamente al reducir `last_number`.

Las filas históricas y las sesiones anteriores se conservan íntegramente. Para
el prefijo autorizado dejan de reservar números o impedir la reutilización de
códigos retirados. Los códigos vigentes, los genéricos, los borradores activos,
las reservas posteriores y el historial posterior siguen protegidos. Reabrir
una sesión anterior en borrador vuelve a considerar sus reservas. Los campos
de referencia anterior siguen siendo trazabilidad, no reservas del nuevo ciclo.

Validar una aplicación real dentro de una transacción que se revierte, además
de la vista previa. Confirmar que el contador final no consumió el folio de prueba.
El cambio es Python puro y no requiere actualización de esquema ni recargar datos
maestros; requiere reiniciar los procesos Odoo para cargar el código.
