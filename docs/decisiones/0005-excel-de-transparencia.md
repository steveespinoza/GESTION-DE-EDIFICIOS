# Excel de transparencia por unidad y periodo

## Contexto

El propietario necesita comprobar el reparto de los servicios y conciliar sus cargos y pagos. La ruta por unidad del sistema anterior construye un Excel del edificio completo. Elegí limitar el detalle a la unidad autorizada y conservar los agregados del proveedor necesarios para explicar su cuota.

El estado de cuenta refleja movimientos vigentes. Un recibo PDF conserva una versión emitida. La descarga de Excel consulta el estado actual para un periodo de cargos y debe expresar esa diferencia.

## Decisión

El SuperAdmin y el propietario descargan el archivo desde el estado de cuenta de la unidad. El propietario accede únicamente a sus unidades. Una unidad ajena y una inexistente responden igual: 404. El edificio de la ruta administrativa debe coincidir con la unidad. La descarga requiere sesión y usa `Cache-Control: no-store`.

El archivo tiene cinco hojas:

| Hoja | Contenido |
| --- | --- |
| Resumen | Edificio, unidad, periodo, fecha de consulta de vencimientos y generación en Lima. Cargos, aplicaciones y pendiente del periodo, pendiente anterior, pendiente total hasta el periodo, parte vencida y crédito disponible actual. |
| Cargos | Periodo y servicio de todos los cargos de la unidad hasta el periodo elegido. Original, ajustes, importe vigente, aplicaciones netas, pendiente, vencimiento y estado. El identificador del cargo queda como comentario de su servicio. |
| Reparto | Solo los servicios del periodo elegido: cobertura, criterio, total original del proveedor y número de unidades incluidas al emitir. Para servicios medidos incluye volumen del proveedor, consumo individual agregado, volumen común, lecturas y consumo de esta unidad, partes propia y común teóricas y asignadas y diferencia de redondeo. Para reparto lineal muestra cuota teórica, cargo asignado y diferencia. Los identificadores propios de factura y cargo quedan en un comentario del servicio. |
| Pagos | Todos los pagos confirmados de esta unidad: fecha recibida, referencia, importe, aplicación hasta el periodo, aplicación posterior, crédito actual y diferencia de conciliación. Debajo aparecen sus aplicaciones con fecha en Lima, referencia, periodo y servicio de destino, importe inicial, liberado, neto e identificadores propios. |
| Ajustes | Historial de cargos hasta el periodo: servicio, revisión, importe anterior y revisado, diferencia, fecha en Lima y motivo. |

El pendiente suma una vez los cargos del periodo elegido y los saldos pendientes de cargos anteriores. Excluye cargos posteriores. No vuelve a sumar los arrastres ni vuelve a restar el crédito. Los cargos anteriores ya pagados se conservan en el detalle para explicar sus movimientos.

La hoja Pagos incluye aplicaciones posteriores para conciliar cada monto recibido con sus aplicaciones netas y su crédito actual. Esto no convierte la descarga en un cierre histórico: los pagos y ajustes realizados después de ese mes ya están reflejados. Las hojas explican ese alcance junto a los importes.

El reparto usa la cantidad de cargos de la factura original. Agregar unidades después no cambia el divisor. Conserva los importes asignados al emitir y muestra por separado las cuotas teóricas sin redondear. Los ajustes posteriores modifican el cargo vigente, sin presentar esa diferencia como un reparto nuevo del proveedor. Los importes fuente usan céntimos y las lecturas usan milésimas; Excel recibe números y fechas tipados, con fórmulas y resultados calculados para las operaciones derivadas.

El archivo no contiene nombres, números de unidad, lecturas, cargos individuales ni pagos de otras unidades. Los textos aportados por usuarios se escriben como texto, sin conversión automática a fórmulas o enlaces.

## Contrato y operación

- `GET /api/admin/buildings/{building_id}/units/{unit_id}/transparency.xlsx`
- `GET /api/owner/properties/{unit_id}/transparency.xlsx`
- Parámetros obligatorios `billing_year` (2020–9999) y `billing_month` (1–12). Sin cargos de la unidad en ese periodo: 409. Parámetros inválidos: 422.

La consulta adquiere el mismo bloqueo compartido de edificio que el estado de cuenta y lo conserva durante la lectura de facturas y agregados. Los escritores financieros esperan, evitando mezclar datos de antes y después de un pago o ajuste.

El backend genera el XLSX en memoria con una dependencia Python incluida en el archivo de versiones bloqueadas. La respuesta es un adjunto con nombre generado a partir del periodo y un fragmento del identificador. No crea un recibo, no escribe en la base ni necesita S3. Esta entrega no requiere migración ni nuevas variables de entorno. El despliegue debe instalar las dependencias actualizadas del backend antes de servir la nueva interfaz.

## Verificación y alcance restante

Las [pruebas de exportación](../../backend/tests/test_transparency.py) cubren reparto lineal de 100.00 entre tres unidades, parte común medida, divisor histórico, pagos parciales, crédito, ajustes con liberación y aplicaciones posteriores, acceso por rol y edificio, periodo vacío y textos con apariencia de fórmula. Las [pruebas del PDF](../../backend/tests/test_receipts.py) conservan su cobertura al compartir la selección de cargos del periodo.

El [recorrido local](../verificacion.md#recorrido-del-excel-de-transparencia) documenta descarga, fórmulas, revisión visual e interfaz. El [PDF consolidado](0006-pdf-consolidado-mensual.md), los [recibos por lote](0007-recibos-por-lote.md), el [Excel mensual](0008-excel-mensual-del-edificio.md) y el [histórico de cobranzas](0009-excel-historico-de-cobranzas.md) tienen decisiones propias.
