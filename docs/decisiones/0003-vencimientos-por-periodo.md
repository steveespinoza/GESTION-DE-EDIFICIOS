# Vencimientos por edificio y periodo

Fecha: 17 de noviembre de 2026.

## Contexto

La cobranza agrupa los servicios de una unidad por mes contable. El sistema anterior mezclaba fechas de cobertura del proveedor con vencimientos de cobro y también permitía indicar una fecha al generar el recibo mensual. La fecha de fin de una factura no demuestra cuándo debe pagar el propietario.

## Decisión

Definí una fecha límite por edificio, año y mes contable, común a sus unidades y servicios. El SuperAdmin la registra desde «Cobranzas» con un motivo. Los periodos ya facturados se pueden seleccionar en el formulario. Los cargos de servicios que se añadan después al mismo periodo usan la fecha vigente de ese periodo.

Cada cambio crea una revisión con fecha, motivo, cuenta y momento de registro. La API recibe la revisión conocida y una clave de solicitud. El bloqueo del edificio serializa los cambios con facturas y pagos; una revisión antigua obtiene `409` y repetir la misma solicitud devuelve el registro original. La lectura de cobranzas y del estado de cuenta mantiene el bloqueo compartido del edificio mientras consulta fechas y movimientos.

Un cargo está vencido cuando conserva saldo y su fecha límite es anterior al día actual de `America/Lima`. Durante la fecha límite todavía está por vencer. Las respuestas incluyen `as_of`, que indica el día usado al consultar. El total vencido es una parte del pendiente, después de ajustes, aplicaciones y liberaciones. El crédito conserva su conciliación automática y su orden contable actual.

Los periodos sin fecha explícita muestran «Sin vencimiento» y su saldo sigue formando parte del pendiente. La migración no asigna fechas a registros anteriores. El arrastre conserva la fecha del periodo de origen: mover su constancia a otro mes no renueva el plazo ni duplica la deuda. Un cambio de vencimiento modifica su clasificación actual y conserva las fechas anteriores en el historial.

## Contratos y operación

- `GET /api/admin/buildings/{building_id}/collections`: saldos por unidad y periodo, vencimientos, total pendiente, total vencido e historial. Los filtros de periodo y deuda vencida se aplican en la interfaz sobre esta respuesta.
- `POST /api/admin/buildings/{building_id}/collection-deadlines`: registra una revisión y devuelve `201`; un reintento idéntico devuelve `200`.
- Los estados de cuenta de ambos roles añaden `as_of` y `overdue_balance`; cada cargo añade `due_date` y `overdue`.
- La migración `0014_collection_deadlines` crea una tabla de historial y conserva los movimientos contables. Aplicarla antes de desplegar backend y frontend, en ese orden.
- Para revertir la aplicación, restaurar primero el frontend y después el backend, conservando la tabla. El descenso de esquema a 0013 solo se permite si la tabla está vacía; con historial registrado se bloquea para evitar su pérdida.

La emisión y las versiones de los recibos PDF siguen pendientes. Cuando se incorporen, deben tomar la fecha vigente y conservarla en la versión emitida.

## Evidencia

[Pruebas de API](../../backend/tests/test_deadlines.py), [concurrencia](../../backend/tests/test_credit_concurrency.py), [migración con movimientos previos](../../backend/tests/test_deadline_migration.py) y [recorrido de navegador](../verificacion.md#recorrido-de-vencimientos-y-cobranzas).
