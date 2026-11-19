# PDF consolidado mensual por edificio

## Contexto

La administración necesita contrastar las facturas del proveedor con los cargos de cada unidad y conocer sus pendientes. El sistema anterior ofrece un resumen por servicio y un desglose por unidad. Conservé esas dos vistas e incorporé aplicaciones de pagos, ajustes, saldos anteriores, vencimientos y crédito conforme al estado de cuenta.

## Decisión

El SuperAdmin descarga el consolidado desde Cobranzas, eligiendo un periodo con cargos. El reporte contiene todas las unidades registradas del edificio, aunque una unidad no tenga cargos de ese mes. Los filtros de la lista de cobranzas no recortan el PDF; el selector del documento define su periodo.

El documento muestra:

- Edificio, dirección, mes, generación y fecha de evaluación en Lima, vencimiento del mes y cantidad de unidades registradas.
- Pendiente hasta el periodo, parte vencida de ese pendiente y crédito disponible actual, separados.
- Facturas del mes por servicio: importe original del proveedor, ajustes de los cargos, cargos vigentes, aplicación neta y pendiente del mes. Incluye totales de edificio.
- Cada unidad y su propietario actual, cargos del mes, aplicado al mes, pendiente del mes, pendiente anterior, total pendiente, parte vencida y crédito actual. Las unidades sin cargos del mes se identifican expresamente.

Los cargos del mes incluyen sus ajustes auditados. Aplicado al mes suma aplicaciones netas a esos cargos, después de liberaciones, independientemente de cuándo se recibió el pago. No representa efectivo recibido durante ese mes.

El pendiente anterior es el saldo vigente de los cargos cuyo periodo precede al seleccionado. El total suma ese pendiente y el del mes una sola vez; excluye cargos posteriores y no vuelve a sumar arrastres. El crédito actual considera todos los periodos y no se resta de nuevo, porque el pendiente ya incluye sus aplicaciones.

Cada cargo conserva su vencimiento de origen. El importe vencido se calcula sobre el pendiente actual y la fecha de Lima. Un cargo sin fecha no se cuenta como vencido; el día de vencimiento aún está dentro de plazo.

La descarga refleja el estado vigente y lo indica en el PDF. Incluye pagos y ajustes posteriores al mes seleccionado; no reconstruye un cierre histórico ni sustituye una versión emitida del recibo individual. El nombre de la unidad y el propietario corresponden al registro actual.

## Consistencia y permisos

La lectura usa los mismos importes de cargo, ajustes, aplicaciones netas y crédito del estado de cuenta. Adquiere un bloqueo compartido del edificio y lo mantiene durante las consultas y la generación. Los escritores financieros adquieren antes el bloqueo exclusivo, evitando mezclar importes de antes y después de un movimiento. La lectura requiere cuatro consultas, sin consultar cada unidad por separado.

Solo SuperAdmin tiene acceso, incluso cuando el propietario pertenece al edificio. Las consultas limitan tanto las unidades como las facturas al edificio solicitado. No se incluyen registros de otro edificio.

El PDF usa A4 horizontal, repite encabezados de tablas y pagina el detalle. Los anchos numéricos consideran los importes de las unidades y sus totales para conservar los céntimos en una sola línea. Los textos se escapan antes de renderizarlos y comparte el bloqueo de fuentes con el PDF individual para proteger la generación simultánea.

## Contrato y operación

`GET /api/admin/buildings/{building_id}/consolidation.pdf`, con `billing_year` entre 2020 y 9999 y `billing_month` entre 1 y 12, devuelve un adjunto `application/pdf`, sin caché. Sin sesión responde 401; un propietario recibe 403; edificio inexistente, 404; periodo sin cargos, 409; parámetros inválidos, 422.

La respuesta se genera en memoria y se descarga directamente. No guarda archivos en S3 ni crea registros de recibo. No requiere migración, nuevas dependencias ni variables de entorno. Para habilitarlo se despliegan backend e interfaz; volver a las versiones anteriores revierte la funcionalidad sin cambios de esquema.

## Verificación y pendientes

Las [pruebas del consolidado](../../backend/tests/test_consolidation.py) comparan el detalle con los estados de cuenta, concilian servicios, crédito y ajustes con liberaciones, excluyen periodos posteriores, mantienen unidades nuevas sin cargos y aíslan dos edificios y dos propietarios. También comprueban el bloqueo frente a un pago concurrente, importes altos completos, texto especial, paginación y generación simultánea.

El [recorrido local](../verificacion.md#recorrido-del-pdf-consolidado-mensual) documenta descarga, revisión de páginas, teclado, carga, error, reintento, vacío y móvil. Los [recibos por lote](0007-recibos-por-lote.md) y el [Excel mensual](0008-excel-mensual-del-edificio.md) tienen decisiones propias. Siguen pendientes el recorrido desplegado y el Excel histórico de cobranzas.
