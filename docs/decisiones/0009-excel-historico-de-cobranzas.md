# Excel histórico de cobranzas

## Contexto y decisión

El sistema anterior exporta una hoja por periodo con la deuda y los pagos de cada unidad. Conservé la consulta por periodo y distinguí los cargos propios, los pendientes anteriores y las aplicaciones de pagos. El resumen cuenta cada saldo una sola vez y mantiene separado el crédito actual, conforme a Cobranzas y el estado de cuenta.

El SuperAdmin descarga todo el histórico desde Cobranzas. Los filtros de periodo y vencidos de la lista no reducen el archivo. Se incluyen los periodos que tienen cargos registrados, ordenados del más reciente al más antiguo, incluso si ya están pagados o ajustados a cero. No se inventan hojas para meses sin cargos. Los periodos futuros registrados también aparecen, igual que en Cobranzas.

## Hojas y alcance financiero

| Hoja | Contenido |
| --- | --- |
| Resumen | Edificio, generación y evaluación de vencimientos en Lima. Tabla por periodo con cantidad de unidades con cargos, cargos vigentes, aplicaciones netas, pendiente propio y parte vencida. El total suma únicamente esos importes propios. El crédito disponible actual figura separado, con detalle de las unidades que lo conservan. |
| Periodo AAAA-MM | Todas las unidades registradas del edificio y su propietario actual. Cargos y aplicaciones del periodo, pendiente propio, pendiente anterior y total hasta el periodo; parte propia vencida, vencimiento, estado y participación en los cargos del mes. |

El pendiente anterior suma los saldos vigentes de los periodos previos de la misma unidad. El total hasta el periodo agrega ese pendiente al propio. Es una vista acumulada: no se suman entre sí los totales acumulados de distintas hojas. El Resumen enlaza solo los pendientes propios, por lo que cada cargo pendiente se cuenta una vez. Los arrastres conservan sus cargos de origen y no se agregan como cargos nuevos.

Las aplicaciones son netas de liberaciones por ajustes y corresponden al periodo del cargo, aunque el dinero se recibiera en otro mes. No representan efectivo recibido durante el periodo. El crédito actual ya refleja sus aplicaciones automáticas; no se vuelve a descontar del pendiente ni se distribuye entre hojas históricas.

El archivo refleja los movimientos vigentes al descargar, incluidos pagos y ajustes posteriores al periodo. No reconstruye un cierre contable de cada mes. Números de unidad y propietarios corresponden al registro actual. Una unidad sin cargos del periodo conserva su pendiente anterior, se identifica como «Sin cargos» y tiene cero en sus importes propios. El día del vencimiento todavía está dentro de plazo; la fecha de evaluación es la de Lima.

Los importes y fechas son valores tipados. Las fórmulas calculan pendientes y totales, enlazan el resumen con las hojas y llevan el saldo anterior desde el periodo registrado precedente. Los identificadores internos permanecen ocultos, fuera del área de impresión, y participan en la ordenación para conservar los vínculos de la unidad. Números como `001` y `1` no se confunden. Los textos aportados por usuarios se escriben como texto, sin convertirse en fórmulas ni enlaces. Se incluyen resultados calculados para lectores que no recalculan al abrir.

## Consistencia, acceso y operación

La lectura reutiliza Cobranzas y mantiene su bloqueo compartido del edificio durante la consulta de unidades, crédito y generación del archivo. Realiza cuatro consultas, sin consultar por unidad o periodo. Los escritores financieros esperan a ese bloqueo para que el archivo no mezcle estados de antes y después de un pago o ajuste.

`GET /api/admin/buildings/{building_id}/collections.xlsx` descarga el histórico completo, sin parámetros de periodo. Solo SuperAdmin tiene acceso. Responde 401 sin sesión, 403 por rol, 404 para un edificio inexistente y 409 cuando no hay periodos con cargos. Devuelve un adjunto XLSX con `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`.

La descarga es directa y se genera en memoria. No requiere migración, dependencias adicionales, variables nuevas ni S3. No modifica cargos, pagos o recibos. Se despliegan backend e interfaz juntos; volver a las versiones anteriores revierte la capacidad sin cambios de esquema ni datos.

## Verificación

Las [pruebas del histórico](../../backend/tests/test_collection_history_excel.py) comprueban conciliación con Cobranzas y el Excel mensual, pagos parciales, cambios de año, meses omitidos, ajustes y liberaciones, crédito y su uso posterior, unidades sin cargos, importes cero, permisos, textos literales y bloqueo frente a un pago concurrente. El [recorrido local](../verificacion.md#recorrido-del-excel-histórico-de-cobranzas) incluye descarga real, fórmulas y revisión visual. Quedan pendientes la apertura en Microsoft Excel de escritorio y el entorno desplegado.
