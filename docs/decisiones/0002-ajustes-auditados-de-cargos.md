# Ajustes auditados de cargos con movimientos

Fecha: 17 de noviembre de 2026. Alcance: FAC-02, COB-02 y POR-01.

## Contexto

La aplicación protege las facturas que ya tienen pagos o arrastres. El sistema anterior recalculaba sus cargos directamente. Para corregir esos importes y conservar su historia, el ajuste debe identificar el cargo original, explicar la diferencia y reconciliar el dinero que ya se recibió.

## Decisión

Registro el nuevo importe vigente de un cargo y conservo el original. El SuperAdmin indica la unidad, el nuevo importe y el motivo desde la factura. Cada ajuste guarda el importe anterior, el nuevo, su diferencia, revisión, fecha y responsable. El importe vigente admite cero; el límite monetario y los dos decimales coinciden con los de facturación.

Una factura abierta conserva su formulario de corrección. Una factura con pagos o arrastres admite ajustes monetarios por unidad. El ajuste conserva las lecturas, los consumos, las fechas, los archivos y el importe del proveedor. La ficha distingue el importe original del proveedor del total vigente de cargos. Una modificación posterior se registra con otro ajuste.

Cuando el nuevo importe queda por debajo del dinero aplicado, libero solo el excedente. Recorro primero las aplicaciones más recientes por fecha e identificador y devuelvo ese dinero al crédito de su pago de origen. La aplicación anterior conserva su importe; una liberación separada queda vinculada al ajuste. Si el crédito vuelve a cubrir el mismo cargo, se registra otra aplicación con identidad propia.

El crédito liberado se concilia automáticamente con los cargos pendientes más antiguos de la misma unidad. Por cada pago, la suma de sus aplicaciones vigentes y su crédito disponible coincide con el importe recibido. Una reducción sobre deuda sin pagar disminuye el pendiente; el crédito procede exclusivamente de dinero que ya estaba aplicado. Un aumento puede consumir crédito disponible o dejar una deuda nueva en el mismo cargo.

El estado de cuenta muestra el importe original, la suma de ajustes, el importe vigente y los pagos aplicados. En cada aplicación muestra el importe inicial, lo liberado y su importe vigente. Ambos roles consultan el historial de ajustes con el alcance de su unidad. Las constancias de arrastre conservan el importe de su registro y muestran el saldo actual del cargo ajustado.

## Concurrencia y recuperación

La operación usa el bloqueo del edificio y se confirma junto con las liberaciones, el crédito y sus nuevas aplicaciones. Una clave de solicitud por cargo admite reintentar la misma operación. Reutilizarla con otros datos o enviar una revisión antigua devuelve un conflicto. El fallo de cualquiera de las etapas revierte la operación completa.

La migración `0013_audited_charge_adjustments` agrega identidad a las aplicaciones existentes y conserva los importes y sus datos de auditoría. PostgreSQL genera el identificador cuando un backend anterior inserta una aplicación sin ese campo, de modo que los registros de pagos pueden continuar durante la transición. Los ajustes se utilizan después de actualizar backend y frontend. Incorpora los ajustes y las liberaciones. El descenso a `0012_automatic_credit_and_carry` se admite antes de registrar ajustes; con historial nuevo se bloquea para preservarlo. La recuperación con movimientos requiere una corrección hacia adelante o restaurar una copia completa del entorno.

Backend y frontend comparten el contrato nuevo: identidad de aplicaciones, importes vigentes y liberados, historial de ajustes e identificadores de cargos. La migración se aplica antes de desplegar ambas partes. Esta entrega se verificó sobre PostgreSQL aislado; la aplicación en Neon y el despliegue quedan pendientes.

Evidencia: [API y conciliación](../../backend/tests/test_charge_adjustments.py), [concurrencia](../../backend/tests/test_credit_concurrency.py), [migración con datos](../../backend/tests/test_credit_migration.py) y [recorrido de interfaz](../verificacion.md#recorrido-de-ajustes-auditados).
