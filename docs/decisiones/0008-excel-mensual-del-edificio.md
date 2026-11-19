# Excel mensual del edificio

## Contexto y decisión

La administración necesita descargar el consolidado por unidad y explicar el reparto de los servicios. El sistema anterior incluye una matriz de parámetros, lecturas y partes propia y común. Conservé esas capacidades y concilié sus importes con el PDF consolidado y el estado de cuenta vigente.

El SuperAdmin descarga el Excel desde Cobranzas y elige un periodo con cargos. Incluye todas las unidades registradas del edificio. Los filtros de la lista no reducen el archivo; el selector del Excel define su periodo.

## Hojas y cálculos

| Hoja | Contenido |
| --- | --- |
| Consolidado | Edificio, periodo, vencimiento y fechas de generación y evaluación en Lima. Una fila por unidad con propietario actual, cargo vigente por servicio, cargos y aplicaciones del mes, pendiente del mes, pendiente anterior, pendiente total, parte vencida y crédito actual. Identifica unidades sin cargos del periodo. |
| Matriz de servicios | Una fila por factura: servicio, estrategia, cobertura, importe del proveedor y divisor original. Para servicios medidos muestra volumen del proveedor, consumo propio agregado, volumen común, tarifa y cuota común teóricas. Para lineales muestra cuota teórica. Incluye ajustes, cargos vigentes, aplicaciones netas, pendiente y diferencia entre reparto original y factura. |
| Detalle | Una fila por cargo del mes con unidad, propietario, servicio, lecturas, consumo propio, importes propios y comunes asignados o cuota lineal, cargo original, ajustes, importe vigente, aplicaciones netas y pendiente. |

Los importes monetarios conservan céntimos y las lecturas, tres decimales. La matriz mantiene seis decimales en tarifas y cuotas teóricas para explicar el redondeo. El detalle utiliza los céntimos guardados al emitir; no vuelve a repartir el proveedor. El divisor cuenta las unidades incluidas en esa factura, aunque después se agreguen otras. El consumo guardado incluye los reinicios confirmados de medidor.

Las fórmulas enlazan las tres hojas: el detalle calcula cargo original, vigente y pendiente; la matriz agrega por factura y calcula sus parámetros; el consolidado agrega por unidad y servicio y calcula sus saldos y totales. Se guardan también resultados calculados para lectores que no recalculan al abrir. Los vínculos usan identificadores internos en columnas y una fila ocultas, fuera del área de impresión. La ordenación incluye esos identificadores; números como `001` y `1`, o nombres con comodines, no se confunden. Los textos de usuarios se escriben como texto, sin convertirlos en fórmulas ni enlaces.

El pendiente suma una vez los cargos vigentes del mes y los saldos anteriores. Excluye cargos posteriores y no vuelve a sumar arrastres. Las aplicaciones son netas de liberaciones por ajustes y pueden haberse registrado después del mes elegido; no representan efectivo recibido durante ese mes. El crédito disponible actual permanece separado y no se resta otra vez del pendiente. Los vencimientos se evalúan con la fecha de Lima y el día de vencimiento todavía está dentro de plazo.

La descarga presenta el estado vigente, no reconstruye un cierre histórico. El nombre de unidad y propietario también corresponden al registro actual. Las unidades sin un cargo de cierto servicio conservan esa celda vacía; las de importe cero sí muestran un cargo registrado. Las hojas anchas permiten desplazamiento horizontal y conservan un tamaño de impresión legible, con encabezados y columnas identificadoras repetidas.

## Consistencia, permisos y contrato

La consulta reutiliza el consolidado y mantiene su bloqueo compartido de edificio durante la lectura del detalle y la generación. Son cinco consultas, sin consultas por unidad. Los escritores financieros esperan al bloqueo para impedir que el archivo mezcle importes de antes y después de un pago o ajuste.

`GET /api/admin/buildings/{building_id}/monthly.xlsx` recibe `billing_year` entre 2020 y 9999 y `billing_month` entre 1 y 12. Solo SuperAdmin puede descargarlo. Sin sesión responde 401; propietario, 403; edificio inexistente, 404; periodo sin cargos, 409; parámetros inválidos, 422. Las consultas limitan unidades y facturas al edificio solicitado.

Devuelve un adjunto XLSX con `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`. La interfaz presenta preparación, error y reintento, deshabilita el selector mientras descarga y lleva el foco al aviso. Salir de la pantalla cancela la petición del navegador.

## Operación y verificación

No requiere migración, variables nuevas ni dependencias adicionales. Utiliza la biblioteca de Excel existente, genera en memoria y descarga directamente; no escribe archivos en S3 ni crea recibos. Se despliegan backend e interfaz juntos. Volver a la versión anterior revierte la capacidad sin cambios de datos.

Las [pruebas del Excel mensual](../../backend/tests/test_monthly_excel.py) cubren conciliación, redondeo, consumo común, reinicio, divisor histórico, ajustes, liberaciones, crédito, periodos posteriores, alcance de acceso, texto literal y bloqueo concurrente. El [recorrido](../verificacion.md#recorrido-del-excel-mensual-del-edificio) incluye descarga real, revisión de las tres hojas y comprobación de fórmulas con un lector independiente. El [Excel histórico de cobranzas](0009-excel-historico-de-cobranzas.md) tiene una decisión propia. Queda pendiente el entorno desplegado.
