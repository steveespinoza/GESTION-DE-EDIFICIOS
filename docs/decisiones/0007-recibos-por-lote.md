# Emisión de recibos por lote

## Contexto

La emisión individual conserva versiones, datos financieros y archivos privados. La administración necesita emitir un periodo completo, conocer el resultado por unidad y continuar cuando falle una parte. Elegí guardar el lote y confirmar cada unidad por separado, sin agregar un servicio de tareas en segundo plano.

## Preparación y alcance

El SuperAdmin abre «Emitir recibos por lote» desde Cobranzas. Elige periodo, fecha límite y motivo. Preparar el lote registra o conserva el vencimiento común del periodo y guarda las unidades incluidas en la misma transacción. Si la fecha coincide, reutiliza su revisión. Una revisión antigua se rechaza antes de cambiar datos.

La preparación conserva las unidades registradas del edificio, su número y la versión de recibo vigente de cada una. Las unidades con cargos del periodo quedan pendientes, incluso si están pagadas. Las que no tienen cargos quedan omitidas. Agregar una unidad o un cargo después no cambia esa selección; se prepara otro lote para incluirlos.

El identificador de solicitud permite repetir la preparación con los mismos datos y recuperar el mismo lote, aun cuando su vencimiento ya haya avanzado durante esa preparación. Reutilizarlo con datos distintos devuelve conflicto. Un lote nuevo representa una intención nueva y captura las versiones vigentes en ese momento.

## Emisión y recuperación

La pantalla procesa una unidad por petición y presenta su progreso. Cada petición adquiere el bloqueo exclusivo del edificio, comprueba el lote y la unidad, valida el vencimiento y emite con el mismo caso de uso del PDF individual. Así, una petición no necesita esperar a que termine el edificio completo.

El recibo y el resultado exitoso de la unidad se confirman en una sola transacción. La clave de solicitud de cada recibo deriva del lote y la unidad. Una unidad emitida devuelve su resultado previo ante reintentos o solicitudes concurrentes, sin volver a guardar el PDF ni aumentar la versión. Una respuesta perdida se recupera consultando el lote.

Cada PDF conserva los importes, movimientos y propietario del momento de su emisión. El lote no congela el estado financiero de todas las unidades en un único instante. Los cargos, pagos, ajustes y crédito se obtienen del estado de cuenta al emitir cada unidad; las versiones anteriores se conservan.

| Resultado | Comportamiento |
| --- | --- |
| Pendiente | Puede continuar desde la pantalla del lote. |
| Emitido | Conserva el recibo, su versión y su enlace de descarga autorizado. Repetir la petición no lo cambia. |
| Falló por almacenamiento o generación | Guarda un mensaje seguro, intentos, fecha y último responsable. Permite reintentar esa unidad o todos los fallos recuperables. |
| Falló por cambio de vencimiento, versión o pertenencia de unidad | Conserva los éxitos previos y pide preparar otro lote con los datos actuales. No sobrescribe el cambio de otra sesión. |
| Omitido | No tenía cargos del periodo al preparar. No genera un recibo ni realiza intentos de almacenamiento. |

Un fallo de almacenamiento no revierte el vencimiento ya registrado ni los recibos de otras unidades. El fallo revierte el intento de recibo de esa unidad y guarda su resultado fallido. Si la base falla, no confirma ni el recibo ni su resultado; el cliente consulta el lote antes de continuar.

El usuario puede detener el proceso después de la unidad en curso. Cerrar o recargar la página conserva lo confirmado y los pendientes; el procesamiento no continúa automáticamente con la página cerrada. El historial permite abrir y continuar el lote. Preparar otro lote emite versiones nuevas para las unidades que se procesen; no reemplaza archivos anteriores.

## Persistencia y permisos

La migración `0016_receipt_batches` crea `receipt_batches` y `receipt_batch_items`. Guarda periodo, vencimiento y revisión, motivo, creador, selección de unidades, versiones iniciales, resultados, recibos vinculados e intentos. Las restricciones protegen la solicitud por edificio, la selección única por unidad, los vínculos de recibo y la coherencia entre errores y resultados.

Solo SuperAdmin puede preparar, consultar o procesar lotes. Todas las rutas comprueban el edificio y el lote; una unidad de otro edificio no puede procesarse. El propietario ve únicamente sus recibos en el historial individual existente, conservando sus controles de acceso y sus descargas temporales. Las respuestas del lote usan `Cache-Control: no-store` y las mutaciones requieren el encabezado de sesión.

## Contratos

- `GET /api/admin/buildings/{building_id}/receipt-batches`: historial con contadores.
- `POST` en la misma ruta: prepara el lote. Recibe `request_id`, `billing_year`, `billing_month`, `due_date`, `deadline_revision` y `reason`. Devuelve 201 al crear o 200 al recuperar la misma solicitud.
- `GET /api/admin/buildings/{building_id}/receipt-batches/{batch_id}`: detalle y resultado por unidad.
- `POST /api/admin/buildings/{building_id}/receipt-batches/{batch_id}/items/{unit_id}/issue`: procesa una unidad y devuelve el estado actualizado del lote.

La preparación devuelve 409 ante un periodo sin cargos, una revisión antigua o una solicitud reutilizada con otros datos. Una emisión fallida controlada devuelve 200 con `FAILED` y su política de reintento; el cliente debe comprobar el resultado, no solo el estado HTTP. Un error de transporte obliga a consultar el lote. Las rutas conservan 401 sin sesión, 403 por rol o encabezado de mutación y 404 para recursos fuera del alcance.

## Operación y recuperación

Respaldar la base y aplicar `alembic upgrade head` antes de desplegar el backend y la interfaz. Esta entrega no agrega dependencias ni variables de entorno. El backend necesita los permisos existentes de lectura y escritura en `receipts/`. La validación local usa almacenamiento aislado; la autorización de ese prefijo en S3 real sigue pendiente.

La migración conserva las tablas y recibos existentes y no prepara lotes automáticamente. Puede descender a 0015 cuando no hay lotes. Con lotes existentes, protege el descenso para conservar su historial. Ante una reversión de aplicación, volver al backend y frontend anteriores conservando las tablas nuevas; no eliminar el historial para forzar un descenso.

## Verificación

Las [pruebas de lotes](../../backend/tests/test_receipt_batches.py) cubren éxito parcial, reintentos, versiones, vencimientos, selección de unidades, permisos, fallos y concurrencia. La [migración](../../backend/tests/test_receipt_batch_migration.py) conserva los datos previos y protege el descenso. El [recorrido](../verificacion.md#recorrido-de-recibos-por-lote) comprueba la recuperación de progreso, respuestas perdidas y el acceso de propietarios.
