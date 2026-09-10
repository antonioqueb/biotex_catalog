# Consecutivos del catálogo

Versión `19.0.2.3.0`.

La numeración se comparte por prefijo `GG-FFF-CCC-MMMM` (y `GG-MMMM-FFF-CCC` para las claves anteriores) entre empresas, productos activos y archivados, asistente individual, sesiones de clasificación y reordenamiento por medida. Por ejemplo, después de `CE-LGMD-EDO-EKG-17` se reserva `CE-LGMD-EDO-EKG-18`. Otro prefijo tiene su propia numeración.

El contador persistente conserva el mayor número usado o reservado. Al obtener el siguiente también se consulta el sufijo numérico de las claves reales, el contador almacenado y los antecedentes de las sesiones. Una clave importada con contador vacío sigue contando. La migración inicializa los contadores con los datos existentes sin renumerar productos ni borradores.

Agregar un producto a una sesión reserva un número. Quitar la línea, cancelar o eliminar el borrador no devuelve ese número. Archivar, eliminar o reclasificar un producto tampoco reinicia su secuencia. Por ello pueden existir saltos. Las vistas previas del asistente individual no consumen números; la asignación definitiva se realiza al guardar.

Las reservas de un mismo prefijo se serializan en PostgreSQL, incluida la primera reserva. Una transacción concurrente con una lectura anterior se reintenta mediante el mecanismo nativo de Odoo. Las escrituras de claves estructuradas comprueban que otro producto, incluso archivado, no tenga esa clave. Las referencias históricas sin el formato de clasificación conservan su tratamiento anterior.

Si un borrador anterior contiene una reserva que colisiona, **Generar claves** obtiene un número nuevo antes de preparar la revisión. Si la colisión aparece después de revisar, la confirmación exige abrir de nuevo la revisión. Las referencias ya aplicadas conservan su historial.

Cambiar el prefijo de una sesión obtiene números de la nueva clasificación y conserva el último número reservado de la anterior. Cambiar el orden de las filas no cambia sus números. El reordenamiento por medida utiliza números nuevos después del último conocido, en lugar de reiniciar en 01; sus códigos propios y etiquetas siguen el proceso de actualización existente.

Las pruebas `TestProductSequence` cubren sufijos y contadores importados, archivados, varias empresas, borradores eliminados o cancelados, generadores compartidos, dos solicitudes concurrentes, referencias existentes, colisiones y revisiones, cambio de clasificación y reordenamiento. La prueba concurrente utiliza conexiones independientes y elimina sus contadores temporales; no confirma registros de negocio ficticios.

Referencias técnicas: [reintentos de transacciones de Odoo 19](https://github.com/odoo/odoo/blob/19.0/odoo/service/model.py) y [aislamiento de transacciones de PostgreSQL](https://www.postgresql.org/docs/current/transaction-iso.html).
