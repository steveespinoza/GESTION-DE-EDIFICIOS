# Matriz de paridad funcional

Este proyecto retoma los flujos del sistema de gestión inmobiliaria que desarrollé anteriormente. La tabla recoge lo que debe poder hacer cada usuario en la nueva versión. Los identificadores enlazan los cambios con sus pruebas. Cada fila se dará por verificada cuando se pueda reproducir el resultado con el rol correspondiente.

El detalle de cada capacidad está en [Requerimientos](requerimientos.md) y [Casos de uso](casos-de-uso.md). Los escenarios previstos están en [Verificación](verificacion.md).

| ID | Capacidad y criterio de aceptación | Estado |
| --- | --- | --- |
| IDE-01 | SuperAdmin y Propietario ingresan con usuario y contraseña, llegan al panel correcto y pueden salir. Las sesiones vencidas pierden acceso. | Pendiente |
| IDE-02 | El propietario confirma su contraseña vigente al editar el perfil o cambiar la contraseña. El SuperAdmin actualiza datos de un propietario y restablece su contraseña confirmando la propia. | Pendiente |
| EDI-01 | El SuperAdmin lista, crea, abre y edita edificios. Configura nombre, dirección, capacidad, banco, cuenta, CCI, titular y correo de contacto. | Pendiente |
| UNI-01 | El SuperAdmin registra unidades con un propietario nuevo o del catálogo. Una cuenta se reutiliza en distintos edificios. La capacidad y la unicidad del identificador se respetan también ante altas simultáneas. | Pendiente |
| UNI-02 | El SuperAdmin lista unidades con su propietario, busca por número o propietario, consulta la ficha y edita identificador, área y datos del propietario. | Pendiente |
| FAC-01 | El SuperAdmin crea y lista categorías de servicio por edificio, con estrategia lineal o medida. | Pendiente |
| FAC-02 | El SuperAdmin registra la factura del proveedor por periodo con fechas, monto, volumen cuando corresponda, varios adjuntos y comprobante. Consulta el histórico y corrige facturas según el estado contable. Cada servicio tiene como máximo una factura por edificio y periodo. | Pendiente |
| FAC-03 | Se precarga la última lectura pertinente, se aceptan tres decimales y se solicita confirmar un reinicio de medidor. El cargo mide consumo propio y reparte el consumo común. La estrategia lineal divide el cargo entre las unidades. En ambos casos, los cargos suman el monto de origen al céntimo. | Pendiente |
| COB-01 | El propietario reporta un pago externo con comprobante. El SuperAdmin ve los pendientes, vencimientos y pagos por unidad y periodo, registra monto y fecha, conserva o reemplaza el comprobante y consulta el detalle del pago registrado. | Pendiente |
| COB-02 | El pago exacto se aplica al saldo correspondiente. El pago parcial y el excedente dejan saldo o crédito trazable. El arrastre funciona al cambiar de mes o año. La confirmación repetida o concurrente tiene un solo efecto contable. | Pendiente |
| POR-01 | El propietario ve sus unidades en distintos edificios, el resumen de pendientes y el panel de cada unidad. Puede consultar su estado de cuenta por periodo, desglose de cargos y consumos e instrucciones de pago. | Pendiente |
| DOC-01 | El propietario descarga el recibo PDF individual y el Excel de transparencia. El SuperAdmin consulta el histórico mensual y exporta el PDF consolidado, el Excel mensual con consolidado y matriz de servicios, y el Excel de cobranzas con hojas por periodo. Los totales cuadran entre fuentes. | Pendiente |
| DOC-02 | El SuperAdmin genera y regenera recibos por lote para un periodo y fecha de vencimiento. El resultado indica éxito o error por unidad, admite reintentar fallos y mantiene las versiones ya emitidas. | Pendiente |
| INC-01 | El propietario reporta fallas en su unidad o en un área común, con descripción, ubicación opcional y foto opcional. El SuperAdmin ve la bandeja del edificio paginada, filtra por estado, abre el detalle y marca la incidencia como atendida. | Pendiente |
| MAN-01 | El SuperAdmin registra y edita equipos, proveedor y frecuencia. Registra, edita y elimina intervenciones con fecha, costo, proveedor y técnico. El historial y las próximas fechas reflejan las correcciones. | Pendiente |
| MAN-02 | El calendario muestra intervenciones ejecutadas y proyectadas por mes. El catálogo identifica equipos al día, por vencer, vencidos y sin registro. Ambos usan la misma regla de fecha. | Pendiente |
| ARC-01 | Se pueden cargar y consultar facturas, fotos, comprobantes y recibos. El acceso a una carga o descarga requiere permiso sobre el edificio, la unidad y el recurso correspondiente. | Pendiente |

## Comprobaciones transversales

- Probar dos edificios, un propietario con unidades en ambos y otro con acceso solo a su unidad. Verificar qué datos obtiene cada usuario en la API, los archivos y los reportes.
- Comparar los resultados contables con casos sintéticos de referencia. Revisar visualmente al menos un PDF de cada tipo y abrir los Excel para comprobar sus hojas y fórmulas.
- Probar el recorrido desde el alta del edificio hasta la conciliación de un pago. Probar también el flujo del propietario para reportar una incidencia y el flujo de mantenimiento desde el alta de un equipo hasta su calendario.
