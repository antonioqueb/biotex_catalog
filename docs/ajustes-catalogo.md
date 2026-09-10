# Ajustes del catálogo en QA — 19.0.3.0.0

La captura del catálogo permite describir un artículo con varias medidas y
presentaciones, conservando una sola identidad de producto.

## Captura con el clasificador

En **Clasificador**, seleccione grupo, familia, clasificador y marca. Agregue los
productos y abra **Editar producto clasificado**. La marca se toma de la selección
principal; el detalle ya no solicita otra marca.

- **Descripción base** y **Unidad indivisible** son obligatorias. La unidad es la
  que se utiliza para comprar, vender y contar el producto.
- **Medidas por componente** admite tantas líneas como sean necesarias, con
  componente, tipo, valor positivo y unidad. Por ejemplo: AGUJA / LARGO / 32 / MM;
  AGUJA / CALIBRE / 21 / G; CABLE / LARGO / 150 / CM.
- **Complemento de descripción** se agrega a la descripción base y las medidas.
  La descripción final se muestra antes de guardar.
- **Presentaciones y códigos de barras** relaciona, por ejemplo, CAJA CON 20,
  CAJA CON 50 y CAJA CON 100 al mismo producto. Cada código tiene una equivalencia
  entera respecto de la unidad indivisible; dos cajas con 50 equivalen a 100 unidades.
- En **Información adicional** se capturan fabricante, distribuidor primario,
  referencia externa, características y las notas separadas de uso, compatibilidad
  e información interna. Fabricantes y distribuidores se pueden crear desde su
  buscador con el permiso de clasificador.

Guardar el detalle actualiza la sesión. **Confirmar clasificación** aplica esos
datos al producto. Los textos descriptivos se normalizan a mayúsculas; los códigos
de barras y referencias externas conservan su escritura.

La ficha general también incluye las pestañas **Medidas**, **Presentaciones y
códigos**, **Uso y notas** y **Claves anteriores**. Una unidad que ya tiene
movimientos no puede cambiarse: las cajas deben definirse mediante equivalencias.

## Validaciones y catálogos auxiliares

Las medidas son opcionales salvo que la familia tenga activado **Medidas
obligatorias**. Los datos opcionales faltantes se muestran aparte del estado de
clasificación. Se conserva la regla existente de fotografías por familia.

Las especialidades no admiten nombres repetidos al normalizar mayúsculas, acentos
y espacios. Las clasificaciones aplican la misma regla dentro de su grupo.
**Configuración → Fabricantes / Distribuidores primarios** permite consultar los
contactos identificados con cada función. La creación desde el clasificador está
limitada a nombre y función comercial; no otorga edición general de contactos.

Los campos anteriores de empaque se conservan como opcionales hasta que se defina
su simplificación. No se crean claves nuevas únicamente por el tamaño de una caja.

## Claves y consecutivos — Dirección

En **Claves y consecutivos** se consultan los últimos números y el historial.
**Reordenar por medida** permite elegir familia, productos o una clasificación
anterior, y filtrar el componente y tipo de medida para ordenar. Las longitudes
MM, CM y M se comparan con su equivalencia en milímetros.

La vista previa muestra las claves propuestas. Al aplicar se asignan nuevos
consecutivos después del máximo usado o reservado, incluidos productos archivados
y claves históricas. Nunca se reinicia en 01 ni se reciclan números utilizados.
Los códigos propios anteriores se conservan como códigos de barras alternos.

## Unificación de duplicados — Dirección

En la lista de productos, seleccione registros del mismo artículo y use
**Acciones → Unificar duplicados**. Elija el producto que se conservará y revise
la unidad y las existencias de los seleccionados antes de aplicar.

El asistente consolida existencias por empresa y ubicación mediante ajustes de
inventario de Odoo. Transfiere códigos de presentación y claves anteriores al
destino y archiva los registros de origen con su relación al producto conservado.

Se exige la misma empresa y unidad, una sola variante, ausencia de seguimiento
por lote y costos iguales donde exista stock. Reservas, cantidades negativas,
paquetes, propietarios, movimientos pendientes, sesiones abiertas y documentos
comerciales relacionados con los registros de origen requieren conciliación
antes de unificar. Los documentos históricos conservan sus referencias.

La instalación no fusiona productos por similitud de nombre ni reordena claves
automáticamente. Las medidas estructuradas se capturan explícitamente; no se
infieren de descripciones importadas que puedan ser ambiguas.
