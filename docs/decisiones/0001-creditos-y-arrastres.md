# Crédito automático y arrastres por cargo

Fecha: 17 de noviembre de 2026. Alcance: COB-02.

## Contexto

El pago ya conservaba el excedente como crédito, pero ese dinero quedaba sin aplicación posterior. También faltaba registrar el saldo de un cargo al pasar a otro periodo. El estado de cuenta sumaba los cargos originales de todos los meses.

## Decisión

Aplico automáticamente el crédito dentro de su unidad. Al emitir o corregir una factura y al confirmar un pago, consumo primero los pagos con crédito más antiguos por fecha de registro e identificador. Los cargos se atienden por año, mes, fin de cobertura e identificador de factura. Una cuenta con varias propiedades conserva un saldo independiente en cada unidad.

El año y mes del pago pasan a ser su periodo de referencia. Antes limitaban la aplicación inicial; ahora el dinero cubre todos los cargos ya emitidos y el excedente se reserva para los siguientes. El importe recibido y la referencia del pago conservan su valor. La misma regla se usa al aprobar un reporte del propietario.

Cada aplicación conserva su importe, cargo, fecha y responsable. La aplicación de un crédito previo se identifica como automática. Las aplicaciones y el crédito disponible reconcilian con el importe del pago de origen. El filtro mensual también muestra pagos anteriores que tienen aplicaciones a cargos del mes consultado.

El arrastre es una constancia del saldo pendiente de un cargo al registrarse en un periodo posterior con facturación. Conserva el cargo original, el importe pendiente, el periodo de destino, la fecha y el responsable. La clave por cargo y periodo impide duplicarlo. Los meses sin facturas se omiten: diciembre puede arrastrarse directamente a febrero. Una factura registrada fuera de orden también registra el saldo pendiente hacia los periodos posteriores existentes.

Los arrastres mantienen el importe de su registro aunque un pago posterior reduzca el saldo. La pantalla muestra ambos valores y el total pendiente cuenta una sola vez el cargo original. El primer pago o arrastre bloquea la corrección directa de la factura de origen; los ajustes de esas facturas siguen pendientes de otra entrega.

## Consecuencias y recuperación

La emisión, las aplicaciones, el crédito, los arrastres y los bloqueos se confirman en la misma transacción bajo el bloqueo del edificio. Un fallo revierte todos esos cambios. Las consultas conservan su comportamiento de solo lectura.

La migración `0012_automatic_credit_and_carry` conserva importes existentes y completa la fecha y el responsable de las aplicaciones anteriores a partir del pago. Los créditos anteriores se concilian en la siguiente emisión, corrección o confirmación; la migración no aplica dinero retroactivamente. El rollback del esquema permite volver a `0011_add_report_proof_versions` mientras no existan aplicaciones automáticas o arrastres. Con movimientos nuevos, la migración rechaza el descenso para preservar su trazabilidad; debe mantenerse el esquema y corregirse hacia adelante o restaurarse una copia completa del entorno.

La API agrega `carry_forwards` al estado de cuenta y `applied_at`, `applied_by` y `automatic` a las aplicaciones. Backend y frontend se despliegan con el mismo contrato, después de aplicar la migración.

Verificación: [créditos y arrastres](../../backend/tests/test_credit_and_carry.py), [concurrencia](../../backend/tests/test_credit_concurrency.py), [migración con datos](../../backend/tests/test_credit_migration.py) y [recorrido de interfaz](../verificacion.md#recorrido-de-crédito-automático-y-arrastres).
