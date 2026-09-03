# Biotex - Catálogo maestro

Módulo para **Odoo 19 Enterprise** · Alphaqueb Consulting SAS · Proyecto Biotex (fase 1).

Grupo > familia > clave, descripción estructurada, marcas, fotos, estado de clasificación, asistentes de clasificación, sinónimos, etiqueta QR

## Dependencias
`biotex_base`, `product`, `stock`, `purchase`

## Instalación
1. Clonar dentro del `addons_path` del servidor Odoo 19 junto con los demás módulos `biotex_*`.
2. Actualizar lista de aplicaciones e instalar `biotex_catalog`.

## Asistente de clasificación (clasificación masiva)

Menú **Catálogo > Asistente de clasificación**. Pantalla OWL de tres etapas para procesar
muchos productos con una misma clasificación:

1. **Selecciona clasificación** — grupo, familia, clasificador y marca, en cascada: cada nivel
   limita el siguiente. Se puede colapsar para dejar sitio a las etapas 2 y 3.
2. **Busca y agrega productos** — búsqueda paginada sobre el catálogo por nombre, clave,
   referencia de fabricante, código de barras, clave alterna, clave SICAR o sinónimo. También
   se puede colapsar.
3. **Actualiza nombres y unidades** — tabla editable con orden por arrastre, nombre actual,
   nombre anterior, unidad de medida, referencia generada y consecutivo.

### Modelo de datos

| Modelo | Papel |
| --- | --- |
| `biotex.classification.session` | Sesión de trabajo: usuario, estado, los cuatro niveles y la clave `class_code`. Persiste, así que "Guardar y salir" se retoma desde **Catálogo > Sesiones de clasificación**. |
| `biotex.classification.session.line` | Un producto de la sesión: orden, nombre anterior (foto del nombre al agregarlo), nombre propuesto, unidad, consecutivo reservado y referencia generada. |

La clasificación reutiliza los modelos que ya existen —`biotex.group`, `product.category`
(familia), `biotex.classifier` y `biotex.brand`—; no se duplica la jerarquía.

### Reglas de la iteración 1

- **El consecutivo se reserva al agregar el producto y no cambia al reordenar.** El orden de la
  tabla es prioridad de trabajo; el consecutivo es identidad. Solo se renumera la sesión completa
  si cambia la clasificación, porque entonces cambia el prefijo y la referencia entera deja de valer.
- **Nada se escribe en `default_code` hasta confirmar.** Mientras la sesión está en borrador la
  referencia es una vista previa; una sesión sin confirmar no quema claves del catálogo.
- Al confirmar (**Generar claves**) se escribe en cada producto: familia, clasificador, marca,
  nombre, unidad de medida, `default_code`, `biotex_consecutive` y —solo si el producto no tenía
  código de barras ni referencia de fabricante— el `barcode`.
- El formato de clave es el del esquema v2 vigente, `GG-MMMM-FFF-CCC-NN`
  (grupo · marca · familia · clasificador · consecutivo), el mismo que produce
  `product.template.action_assign_clave`. Ej. `MC-3M3M-PUN-AGU-01`.
- Fuera de alcance en esta iteración: fotografías, validación final, clasificación por IA y la
  pantalla definitiva de edición. El botón **Editar** de la etapa 3 ya abre un modal
  (`BiotexLineEditorDialog`) con el contrato `onSave(vals)` listo para ampliarlo.

### Asistente guiado (1 a 1)

El asistente anterior sigue disponible en **Catálogo > Asistente guiado (1 a 1)**: cubre fotos,
uso clínico y origen, que la pantalla masiva deja fuera a propósito.

## Licencia
LGPL-3
