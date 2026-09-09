# Clasificador desde Inventario

Dirección puede abrir **Inventario → Productos → Clasificador de catálogo**.
Este acceso abre el mismo asistente disponible en **Catálogo → Asistente de
clasificación**, con las mismas sesiones y productos.

La revisión del 8 de septiembre de 2026 confirmó que los usuarios de Dirección
en producción ya heredaban Clasificador y podían cargar el asistente. Faltaba
un acceso desde Inventario, donde también se consulta el catálogo de productos.
Se añadió ese acceso sin cambiar los permisos de los usuarios.

Las pruebas usan los menús completos que recibe el cliente web, comprueban
que Dirección encuentra el asistente en las dos aplicaciones y que puede
cargarlo sin modo superusuario. Un usuario que tiene únicamente Inventario
no recibe el acceso ni permisos de clasificación.
