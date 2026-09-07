# Acceso de Dirección

En **Distribución de insumos**, seleccione **Dirección** para dar acceso a toda la operación y configuración del negocio. Dirección hereda Clasificador de catálogo; no es necesario elegir ni agregar ese rol por separado.

| Área | Acceso de Dirección |
| --- | --- |
| Catálogo | Productos, variantes, etiquetas, divisiones, grupos, familias, clasificadores, marcas, equipos, especialidades, genéricos, empaques y sinónimos |
| Clasificación | Asistente masivo, sesiones, asistente individual, pendientes, reordenamiento y autorizaciones de fotografías |
| Inventario y compras | Administración de almacenes, ubicaciones, delegaciones, compras y contactos |
| Ventas y contratos | Administración de ventas y listas de precios, contratos y modificaciones contractuales |
| Pagos y contabilidad | Administración contable y solicitudes de pago |

La jerarquía se distribuye según las dependencias de los módulos: `biotex_base` incorpora responsables de inventario, compras y contactos; `biotex_catalog` incorpora Clasificador; `biotex_contract` incorpora administración de ventas; `biotex_payment_request` incorpora administración contable. Los permisos son acumulativos y se propagan a usuarios existentes y futuros de Dirección.

El rol Clasificador conserva sus funciones de clasificación y no hereda Dirección. Se mantienen las compañías autorizadas de cada usuario y las validaciones de negocio, como la conservación de documentos aprobados y la asignación protegida de consecutivos. Dirección es un rol de administración del negocio; no concede administración técnica de Odoo, acceso a contraseñas ni modo superusuario.

Las pruebas `TestDirectionAccess` usan un usuario con solo Dirección y comprueban la herencia, todos los menús del catálogo, permisos de los modelos, creación y edición de grupos/familias/productos/sesiones y la separación respecto de Clasificador.
