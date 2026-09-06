# Correcciones del asistente de clasificación

Fecha: 6 de septiembre de 2026. Módulo existente: `biotex_catalog`, versión `19.0.2.1.0`.

## Diagnóstico y solución

El menú **Catálogo → Asistente de clasificación** abre una acción cliente OWL, `BiotexClassificationWorkspace`. Usa sesiones persistentes, no un modelo transitorio: los borradores deben sobrevivir a **Guardar y salir**.

| Caso | Archivo y causa comprobada en el código anterior | Corrección |
|---|---|---|
| 1. Resumen cortado | `static/src/classification/classification.scss`: `.o_bcw_body` es un contenedor flex vertical y las tarjetas permitían compresión; `.o_bcw_stage` recortaba el contenido con `overflow: hidden`. | Tarjetas con `flex: 0 0 auto`, contenedor desplazable con `min-height: 0`, encabezado con altura mínima, padding, line-height y ajuste de línea. Se conserva el redondeado de la tarjeta. |
| 2. Lupa superpuesta | En el mismo SCSS, `.o_bcw_input` aparecía después de `.o_bcw_search_input` y su shorthand `padding` sobrescribía el padding izquierdo, con la misma especificidad. | Opción A: lupa siempre visible; selector combinado para reservar 40 px mediante `padding-inline-start`. Icono de 16 px más márgenes, sin tapar la escritura. |
| 3. Resultados sin scroll | `.o_bcw_table_wrap` solo definía desplazamiento horizontal. | Máximo de 360 px, `overflow: auto`, espacio estable de scrollbar y región accesible por teclado. Se conserva paginación, ahora de 20 resultados. |
| 4. Agregados visibles | `models/biotex_classification.py`, `workspace_search_products`: contaba y paginaba todos los productos; solo agregaba una bandera `added`. El JS cambiaba la bandera de la fila. | Exclusión por ID en el dominio antes de contar/paginar; eliminación de la fila y nueva consulta después de agregar o quitar. El paso 3 conserva el listado de procesados. |
| 5. Tabla de trabajo sin scroll | Mismo contenedor sin altura máxima; los encabezados no eran fijos. | Scroll interno en ambos ejes y encabezados `sticky` con fondo opaco. Se conservan edición y orden de renglones. |
| 6. Modal inconsistente | `classification.xml` y `classification.scss`: el diálogo vive fuera de `.o_bcw`, por lo que no recibía sus variables ni sus estilos de inputs. Usaba otros colores de respaldo. | Variables y mixin de controles compartidos; tarjetas de datos principales y adicionales, acordeón opcional cerrado al abrir, espaciado de 24 px, botones redondeados y cierre nativo sin borde. |

No se recibió un archivo identificable del mockup antes/después en el espacio de trabajo. La comparación usa el lenguaje visual del asistente existente y los criterios escritos del requerimiento. El HTML `iteracion-1-biotex.html` es un documento de planificación y no corresponde a ese mockup.

## Búsqueda y teclado

- Se conserva el hook nativo `useDebounced` con 300 ms. Enter cancela su ejecución pendiente antes de buscar inmediatamente.
- Cada consulta tiene una versión. Una respuesta antigua no reemplaza resultados de una consulta nueva, incluso durante la espera del debounce.
- El servidor limita cada página a un máximo de 20 artículos y ordena por nombre e ID.
- Después de agregar el último resultado de una página, el servidor ajusta el desplazamiento para no dejar una página vacía fuera del total.
- Flechas arriba/abajo seleccionan un resultado; Enter agrega la selección. Si solo hay una coincidencia total, Enter puede agregarla directamente.
- En modo escáner, se exige una sola coincidencia en el conjunto completo, no únicamente en la página visible.
- Tras agregar se devuelve el foco al buscador. En búsqueda normal se selecciona el texto para poder reemplazarlo; en escaneo se limpia únicamente después del agregado correcto.
- Un error conserva el texto para corregir o reintentar. Las filas ya agregadas se excluyen también al recibir resultados en el cliente.

Se reutilizan `Dialog`, `o_input`, `o_list_table`, botones y utilidades del backend. Los estilos propios se limitan al asistente y sus diálogos. Las tablas personalizadas no se presentan como un `ListRenderer` nativo porque su edición y fuentes de datos son distintas. Referencias: [Dialog de Odoo 19](https://github.com/odoo/odoo/blob/19.0/addons/web/static/src/core/dialog/dialog.xml) y [temporización de Odoo 19](https://github.com/odoo/odoo/blob/19.0/addons/web/static/src/core/utils/timing.js).

## Reclasificación e historial

**Generar claves** consulta el estado actual del catálogo y abre una revisión. Si cambiará una referencia existente, muestra producto, código anterior y código nuevo; exige marcar la aceptación antes de confirmar.

La confirmación vuelve a comprobar la revisión en el servidor. Si cambió una línea o un producto, se solicita revisar de nuevo. La sesión y los productos se bloquean durante la confirmación para evitar una aplicación basada en datos concurrentemente modificados.

Cada aplicación nueva conserva en la línea:

- Referencia anterior y aplicada.
- Descripción de la clasificación anterior y aplicada.
- Usuario que realmente confirmó y fecha de aplicación.

El mismo antecedente se agrega como nota interna al producto. Puede consultarse desde **Catálogo → Sesiones de clasificación → Historial de clasificación**. Las sesiones y líneas aplicadas se protegen contra edición y eliminación ordinarias. Otra reclasificación se realiza en una nueva sesión.

No se reconstruye una autoría desconocida en sesiones históricas. Los campos nuevos permanecen vacíos en antecedentes que no disponen de ese dato. La actualización añade campos al módulo existente y no recrea productos, inventario, adjuntos ni operaciones.

## Casos de aceptación manual

Ejecutar con un usuario **Clasificador de catálogo** en una base de pruebas, con una clasificación válida y al menos 25 productos de prueba. Conservar fecha, usuario, empresa, folio de sesión y capturas. Repetir la revisión visual a 1366×768, 1024×768 y una anchura reducida; comprobar también zoom del navegador.

| ID | Procedimiento | Resultado esperado |
|---|---|---|
| A | Completar grupo, familia, clasificador y marca. Pasar al paso 2 y colapsar/expandir el 1 varias veces. | Código y badge completos, con espacio antes del borde; ningún corte horizontal ni superposición al ajustar el ancho. |
| B | Escribir un nombre largo, una referencia y un código de barras en el buscador. Borrar y volver a escribir. | Lupa siempre visible y texto separado del icono, también con foco y texto residual. |
| C | Buscar un término con más de seis coincidencias. Desplazarse hasta la última fila y avanzar de página. | Scroll interno, encabezados visibles, máximo de 20 resultados por consulta y acceso a todas las páginas. |
| D | Agregar una fila por clic; repetir el mismo término; cambiar de página. Después quitar el producto del paso 3. | Desaparece del buscador al agregar; aumenta el contador una sola vez; reaparece al quitarlo y volver a consultar. |
| E | Agregar al menos doce productos. Desplazar la tabla del paso 3 y editar la última fila. | Altura restringida, encabezados fijos y acceso a todos los renglones sin crecimiento ilimitado. |
| F | Abrir el lápiz de un producto. Revisar principales, desplegar adicionales y cerrar/reabrir. | Mismos colores, radios, foco y botones que el asistente; adicionales cerrados al abrir; controles opcionales conservan datos; X sin caja. |
| G | Usar solo teclado: escribir, esperar resultados, flecha abajo, Enter, escribir el siguiente término. | Se agrega la selección una vez y el foco vuelve al buscador; se puede continuar sin ratón. |
| H | Activar escáner y enviar código+Enter con una coincidencia. Repetir con varias coincidencias y con un error de agregado. | Solo se agrega automáticamente una coincidencia total; el error conserva el código; no se agrega una coincidencia ambigua. |
| I | Simular conexión lenta, buscar A y rápidamente B haciendo que A termine al final. | La pantalla sigue mostrando B y no se reintroducen filas ya agregadas. |
| J | Agregar un producto con referencia anterior y pulsar Generar claves. Cancelar y luego repetir aceptando la revisión. | Cancelar conserva el código anterior; la revisión muestra antes/después y confirmar requiere aceptación. |
| K | Abrir la revisión; modificar el producto o la línea desde otra sesión antes de confirmar. | El servidor rechaza la revisión anterior y exige consultar los cambios de nuevo. |
| L | Confirmar una reclasificación y consultar producto e historial de sesión. Intentar editar/eliminar el antecedente. | Usuario, fecha y antes/después disponibles; IDs del producto y variantes conservados; antecedente protegido. |
| M | Editar un campo opcional, colapsar adicionales y guardar. Probar cantidad de presentación inválida. | El dato válido se conserva; el bloque se abre para mostrar el error del dato inválido. |
| N | Abrir dos peticiones de agregado del mismo producto a la misma sesión. | Una sola línea persistente; no se asigna dos veces el producto a esa sesión. |

## Verificación automatizada

- `node --test tests/classification_search.test.cjs`: carreras de búsqueda, exclusión, agregado repetido, Enter y escáner. Usa dobles de servicios; no sustituye pruebas de renderizado OWL.
- Tests Odoo `TestClassificationWorkspace`: exclusión antes de paginar, límites, corrección de última página, confirmación revisada, cambios posteriores a la revisión, trazabilidad y conservación de identidad. Usan un usuario clasificador sin permisos de superusuario.
- La instalación de pruebas se ejecuta en la copia restaurada; los fixtures de las pruebas de transacción se revierten al finalizar.

Estado de ejecución y evidencia visual: pendiente de completar durante la validación de esta revisión.
