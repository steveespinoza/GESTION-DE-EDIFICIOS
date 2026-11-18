# Recibos PDF individuales con versiones

Fecha: 18 de noviembre de 2026.

## Contexto

El propietario necesita descargar un recibo por unidad y periodo. Los cargos, pagos y vencimientos pueden cambiar después de emitirlo. Regenerar el mismo archivo desde el estado actual borraría el contenido que se entregó anteriormente.

## Decisión

El SuperAdmin emite el recibo desde el estado de cuenta, eligiendo periodo y motivo. Cada emisión crea una versión con una copia financiera, identidad del emisor, momento de emisión, tamaño y huella SHA-256. El PDF tiene una clave nueva en el almacenamiento privado. Las versiones anteriores conservan sus importes, datos de la unidad, instrucciones de pago y vencimiento.

El recibo refleja los saldos vigentes **al emitirlo** de los cargos del mes elegido y de los meses anteriores. No reconstruye un cierre histórico a fin de mes. La copia conserva:

- Cargos vigentes del periodo, importes originales, ajustes, aplicaciones netas, saldo y consumos. Las lecturas y el componente común original permiten contrastar el reparto medido.
- Saldos anteriores todavía pendientes, con servicio, periodo y fecha de origen. Los arrastres no agregan deuda otra vez.
- Pagos aplicados a cargos hasta el periodo seleccionado. Se distingue el importe recibido de la parte aplicada hasta ese periodo, porque el mismo pago puede cubrir cargos posteriores.
- Total pendiente: saldo del periodo más saldo anterior pendiente. Los cargos posteriores quedan fuera del total. El crédito disponible de la unidad se muestra aparte; sus aplicaciones ya están consideradas en los saldos.
- Vencimiento vigente del periodo y vencimientos de los cargos anteriores. Si no hay fecha registrada, el PDF indica «Sin vencimiento definido».

La emisión requiere que la unidad tenga cargos en el periodo. Un pago posterior o un cambio de fecha se consulta en el estado de cuenta actual; para reflejarlo en un PDF, el administrador emite una versión nueva.

## Permisos, reintentos y concurrencia

Solo SuperAdmin emite mediante `POST` y el encabezado de sesión de las demás mutaciones. Ambos roles consultan el historial y descargan archivos según su acceso actual a la unidad. La descarga valida edificio, unidad y recibo antes de generar un enlace temporal de cinco minutos; las respuestas usan `no-store`.

La clave de solicitud hace que un reintento idéntico devuelva la misma versión. Se rechaza reutilizarla con otros datos o emitir desde una revisión antigua. La emisión toma el bloqueo del edificio antes de capturar los movimientos; las restricciones de PostgreSQL protegen la versión y la solicitud. La generación de PDF usa exclusión mutua por proceso porque las fuentes registradas de ReportLab no admiten construir documentos simultáneos con el mismo objeto de fuente.

El registro se confirma después de guardar el PDF. Un fallo del almacenamiento revierte el registro y permite reintentar. Si la carga termina pero falla la confirmación en la base, puede quedar un objeto privado sin referencia; su limpieza por ciclo de vida se podrá incorporar como operación de almacenamiento.

## Despliegue y recuperación

La migración `0015_versioned_receipts` crea `receipts` y conserva los datos anteriores. Aplicarla antes del backend y del frontend, en ese orden. El backend añade ReportLab y reutiliza la configuración de S3 existente, con escritura y descarga en el prefijo `receipts/`.

Para revertir la aplicación, restaurar primero el frontend y después el backend, manteniendo tabla y archivos. El descenso de esquema a 0014 se permite si la tabla está vacía y se bloquea cuando hay recibos, para conservar las versiones emitidas.

El PDF consolidado, Excel y la emisión por lote siguen pendientes. La copia financiera y las versiones individuales constituyen la base para esas entregas.

## Evidencia

[API y contenido del PDF](../../backend/tests/test_receipts.py), [concurrencia de emisión](../../backend/tests/test_credit_concurrency.py), [migración desde 0014](../../backend/tests/test_receipt_migration.py) y [recorrido visual](../verificacion.md#recorrido-de-recibos-pdf-individuales).
