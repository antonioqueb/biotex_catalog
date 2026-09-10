# Reordenamiento del folio: GG-FFF-CCC-MMMM-NN

Desde la versión 19.0.3.2.0 la clave comercial se construye como **Grupo · Familia · Clasificador · Marca · Consecutivo**
(por ejemplo `CE-CBL-EKG-AMBD-01`). Antes era Grupo · Marca · Familia · Clasificador · Consecutivo (`CE-AMBD-CBL-EKG-01`).

## Dónde se aplica

- Un único constructor del prefijo: `biotex.product.sequence._prefix_for(grupo, familia, clasificador, marca)`. Lo usan la sesión del
  asistente masivo (`class_code`), el botón "Asignar clave" del producto y la vista previa del asistente guiado.
- El asistente pinta los segmentos con el orden nuevo (página 1, tabla de la etapa 3 y encabezado del modal de edición). Las referencias
  con el orden anterior se reconocen por su forma (marca de 4 caracteres en el segundo segmento) y se colorean correctamente.
- Etiquetas QR, reportes y búsquedas leen `default_code` tal cual; no construyen la clave, así que no cambian.

## Claves ya generadas con el orden anterior

**No se migran ni se recalculan automáticamente.** Esta decisión debe validarse con el negocio antes de tocar producción; mientras tanto:

- El reconocimiento de claves acepta ambos órdenes (`PREFIX_CURRENT` y `PREFIX_LEGACY` en `product_sequence.py`), así que los productos
  antiguos siguen reservando, buscándose e imprimiéndose igual.
- Al **reclasificar** un producto con clave antigua dentro de la misma clasificación, el asistente conserva esa clave y su nombre (línea con
  `preserve_reference`); solo se actualizan los demás datos.
- Los **contadores** son por prefijo. El prefijo nuevo de una misma clasificación arranca en `01`; el prefijo antiguo conserva su marca de
  agua. Las claves completas no chocan porque el texto es distinto, pero conviven dos numeraciones para la misma clasificación hasta que se
  decida la estrategia.
- Las **sesiones en borrador** al momento de actualizar se renumeran con el prefijo nuevo (aún no han escrito ninguna clave). Las sesiones
  confirmadas conservan su historial.

## Opciones a decidir con el negocio

1. **Dejar las claves antiguas como están** (estado actual). Sin riesgo operativo; dos formatos conviven en el catálogo.
2. **Recodificar con el asistente de reordenamiento** (`biotex.reorder.wizard`) familia por familia: asigna claves nuevas, conserva el
   historial en `biotex.product.code.history` y permite reimprimir etiquetas. Requiere ventana de trabajo y reetiquetado físico.
3. **Migración masiva automática** (script): convertir `GG-MMMM-FFF-CCC-NN` en `GG-FFF-CCC-MMMM-NN` conservando el mismo consecutivo.
   Es la opción más rápida, pero cambia miles de `default_code` de golpe (códigos de barras propios incluidos) y exige reetiquetar.

Hasta que se elija, no ejecutar ninguna recodificación en producción.
