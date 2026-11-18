# Casos de uso

Las referencias de cada caso corresponden a los [requerimientos](requerimientos.md) y a la [matriz de paridad](paridad.md).

## CU-01 · Entrar y salir del sistema

**Actores** — SuperAdmin y Propietario. **Requisito** — `IDE-01`.

1. La persona ingresa su usuario y contraseña. El sistema valida la cuenta y abre el panel de edificios o el portal de propiedades según el rol.
2. Al cerrar sesión, o cuando venza, el sistema retira el acceso a las pantallas protegidas.

Si las credenciales fallan o la cuenta está inactiva, el acceso se rechaza sin revelar cuál dato falló.

## CU-02 · Gestionar los datos de una cuenta

**Actores** — SuperAdmin y Propietario. **Requisito** — `IDE-02`.

1. El propietario modifica su perfil o solicita un cambio de contraseña y confirma la vigente antes de guardar.
2. El SuperAdmin abre la ficha del propietario, actualiza sus datos o inicia un restablecimiento. Para confirmar el restablecimiento, ingresa su propia contraseña.

Si la confirmación es incorrecta o el usuario solicitado queda fuera del ámbito de la operación, se conservan los datos anteriores.

## CU-03 · Configurar un edificio

**Actor** — SuperAdmin. **Requisito** — `EDI-01`.

1. El SuperAdmin abre el listado, registra o edita nombre, dirección y capacidad.
2. Completa las instrucciones de pago con banco, cuenta, CCI, titular y correo de contacto. Desde el listado puede entrar al panel del edificio.

Si la capacidad indicada es menor que el número de unidades registradas, el cambio se rechaza.

## CU-04 · Registrar y consultar unidades

**Actor** — SuperAdmin. **Requisitos** — `UNI-01`, `UNI-02`.

1. En un edificio, registra el identificador y el área. Selecciona un propietario existente o crea una cuenta para asociarla a la unidad.
2. Busca por unidad o propietario. Desde la ficha actualiza el identificador, el área o los datos del propietario.

Si el identificador ya existe en el edificio o se alcanzó la capacidad, la unidad no se registra. El propietario existente conserva una sola cuenta aunque tenga unidades en distintos edificios.

## CU-05 · Registrar y corregir una factura

**Actor** — SuperAdmin. **Requisitos** — `FAC-01`, `FAC-02`, `FAC-03`, `ARC-01`.

1. Selecciona un servicio del edificio o crea uno y elige su estrategia de reparto.
2. Indica el periodo, las fechas, el monto y los adjuntos. En un servicio medido indica el volumen, revisa la lectura anterior y registra la actual por unidad. Si corresponde a un reinicio, lo confirma.
3. El sistema registra la factura y sus cargos. El SuperAdmin abre la ficha desde el historial.
4. En una factura abierta, corrige los datos y explica el motivo. El sistema vuelve a calcular los cargos de las unidades originales y registra el cambio. Para una factura con movimientos contables, selecciona la unidad en «Ajustar un cargo», indica el nuevo importe y explica el motivo. El historial conserva la diferencia, su autor y la fecha. El crédito liberado por una reducción se aplica automáticamente a los pendientes de la misma unidad.

El registro se rechaza si el servicio ya tiene factura para el periodo, si las lecturas corresponden a otro servicio o edificio, o si el consumo total supera el volumen declarado.

## CU-06 · Consultar el estado de cuenta y reportar un pago

**Actor** — Propietario. **Requisitos** — `POR-01`, `COB-01`, `DOC-01`, `ARC-01`.

1. En «Mis propiedades», el propietario consulta sus pendientes y selecciona una unidad.
2. Abre un periodo, revisa los cargos, consumos e instrucciones de pago, y puede descargar su recibo PDF o el Excel de transparencia.
3. Después de pagar por un canal externo, adjunta el comprobante al periodo correspondiente. El comprobante queda disponible para revisión administrativa.

Si la unidad no está asociada a su cuenta, el sistema deniega también el acceso a sus documentos. Adjuntar un comprobante mantiene el saldo hasta que el pago se confirme.

## CU-07 · Confirmar y conciliar un pago

**Actor** — SuperAdmin. **Requisitos** — `COB-01`, `COB-02`, `ARC-01`.

1. En la bandeja de cobranzas, selecciona la unidad y el periodo. Revisa el saldo, el vencimiento y el comprobante recibido, si existe.
2. Revisa la versión vigente del comprobante y registra la fecha y el monto efectivamente recibidos. Puede cargar una copia legible indicando el motivo. El original y las versiones anteriores quedan disponibles en el historial.
3. El sistema registra la confirmación, aplica el monto y actualiza el detalle del pago. Si hay una diferencia, queda identificado el saldo pendiente o el crédito. El crédito se aplica automáticamente a los cargos pendientes de esa unidad y a los que se emitan después. El periodo del pago queda como referencia.

Reintentar la misma aprobación tiene un solo efecto contable. El arrastre al periodo siguiente conserva una referencia a su origen.

Si otra sesión reemplaza el comprobante durante la revisión, el sistema pide actualizar el reporte antes de tomar la decisión. El reemplazo está disponible mientras el reporte esté pendiente.

## CU-08 · Emitir recibos y exportar reportes

**Actor** — SuperAdmin. **Requisitos** — `DOC-01`, `DOC-02`, `ARC-01`.

1. Selecciona edificio y periodo. Consulta el histórico, descarga el PDF consolidado o exporta el Excel mensual y el histórico de cobranzas.
2. Para emitir recibos en lote, indica el vencimiento. Revisa el resultado por unidad y vuelve a intentar los que fallaron.
3. Si solicita una regeneración, se crea una versión nueva con referencia a la unidad y al periodo.

Los documentos reflejan los importes correspondientes a su periodo. La regeneración conserva las versiones emitidas.

## CU-09 · Reportar y atender una incidencia

**Actores** — Propietario y SuperAdmin. **Requisitos** — `INC-01`, `ARC-01`.

1. El propietario selecciona su unidad e indica si la falla está dentro de ella o en un área común. Describe el problema y puede añadir ubicación y foto.
2. El SuperAdmin abre la bandeja del edificio, filtra por estado y consulta el detalle. Cuando termina la atención, marca la incidencia como atendida.

La bandeja pagina los resultados y actualiza el estado tras la atención.

## CU-10 · Llevar el mantenimiento de equipos

**Actor** — SuperAdmin. **Requisitos** — `MAN-01`, `MAN-02`.

1. Registra o edita el equipo, proveedor y frecuencia en meses.
2. Registra una intervención con fecha, costo, proveedor y técnico. Puede corregirla o eliminarla desde el historial.
3. Consulta la última intervención, la próxima fecha, el estado del equipo y el calendario de eventos ejecutados y proyectados.

Al corregir o eliminar la última intervención, el catálogo y el calendario vuelven a calcular las fechas usando el historial disponible.
