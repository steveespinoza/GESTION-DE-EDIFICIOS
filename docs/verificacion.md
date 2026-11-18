# Verificación

La verificación empieza con datos ficticios de dos edificios. Un propietario tiene una unidad en cada edificio y otro tiene una sola unidad. El SuperAdmin puede administrar ambos. Esta distribución permite comprobar el alcance de consultas, pagos, documentos y adjuntos.

## Escenarios de aceptación previstos

| Prueba | Requisitos | Resultado esperado |
| --- | --- | --- |
| Sesión | IDE-01 | Cada rol llega a su panel. El cierre o vencimiento de sesión retira el acceso y la API rechaza el acceso con el rol equivocado. |
| Perfil | IDE-02 | Una contraseña de confirmación incorrecta conserva los datos anteriores. |
| Alta y configuración de un edificio | EDI-01 | El SuperAdmin crea, abre y edita un edificio. Al recargar, persisten los datos generales e instrucciones de pago. La API rechaza una capacidad negativa y bloquea el acceso de propietarios. |
| Alta simultánea de unidades | UNI-01, UNI-02 | Con una plaza disponible, una sola alta se confirma. El número se mantiene único por edificio y la búsqueda encuentra la ficha por unidad o propietario. |
| Factura lineal de S/ 100,00 entre tres unidades | FAC-01, FAC-02, FAC-03 | Se crean tres cargos cuya suma es S/ 100,00. Un segundo registro para el mismo servicio y periodo se rechaza. |
| Factura medida y reinicio del contador | FAC-02, FAC-03 | Se carga la última lectura de ese servicio. El reinicio confirmado conserva la precisión. Con consumo de 120 y volumen declarado de 100, la factura y sus cargos quedan sin registrar. |
| Corrección de una factura | FAC-02, FAC-03 | Se conserva el padrón original, el importe cuadra y la revisión deja constancia del cambio. Una revisión desactualizada, una lectura incompatible o una factura con movimientos impiden el guardado. |
| Pago parcial y cambio de año | COB-01, COB-02 | Un pago de S/ 10,00 sobre S/ 100,00 deja S/ 90,00 de saldo. El arrastre de diciembre a enero referencia su origen. Verificar también pago exacto y excedente. |
| Confirmación simultánea de un pago | COB-02 | Dos intentos de confirmar la misma operación generan un solo pago y un solo conjunto de aplicaciones. La prueba consulta el estado persistido. |
| Acceso a datos y archivos | POR-01, DOC-01, ARC-01 | El propietario con dos unidades puede consultar ambas. El otro solo accede a la suya. Los documentos y enlaces temporales siguen el mismo alcance y caducan cuando corresponde. |
| Reportes y emisión por lote | DOC-01, DOC-02 | El PDF y los Excel reflejan el periodo correcto y sus totales cuadran. El resultado identifica un fallo parcial y permite reintentar esa unidad. Regenerar conserva la versión emitida. |
| Incidencia de área común | INC-01, ARC-01 | El propietario adjunta una foto opcional. El SuperAdmin encuentra el reporte por edificio y estado, lo abre y lo marca como atendido. |
| Corregir la última intervención | MAN-01, MAN-02 | Editar o eliminar la última intervención actualiza la próxima fecha en catálogo y calendario. Una frecuencia mensual al fin de mes produce la misma fecha en ambas vistas. |

## Dónde ejecutar cada prueba

- **Dominio.** Usar pruebas unitarias para prorrateos, lecturas, aplicación de pagos, cambio de periodo y recurrencias.
- **Integración.** Usar una base PostgreSQL aislada para comprobar transacciones, migraciones, alcance por edificio y concurrencia. Verificar el contrato HTTP de los dos roles.
- **Navegador y documentos.** Recorrer alta, facturación, consulta, reporte y validación de pago desde la interfaz. Revisar PDF y Excel con los datos sintéticos y comprobar los flujos de incidencias y equipos.
- **Demo.** Preparar la base desde las migraciones y comprobar que la carga y descarga de archivos funciona con acceso temporal. Revisar teclado, foco, pantallas estrechas y estados de carga, vacío y error. Ante un fallo de la API, buscar su identificador de solicitud en los logs y comprobar que no se expongan credenciales.

Las pruebas y sus resultados se enlazarán desde la [matriz de paridad](paridad.md) a medida que se implementen los requisitos.

## Recorrido con Neon y S3

El 17 de noviembre de 2026 comprobé el frontend y la API ejecutados localmente con PostgreSQL en Neon y archivos privados en Amazon S3. El recorrido usó datos ficticios de dos edificios, tres unidades y dos propietarios.

Desde la interfaz registré el padrón, un servicio lineal y una factura de S/ 100,00 para dos unidades. Se guardaron y descargaron el documento del proveedor y su comprobante. La comparación del contenido confirmó que las descargas correspondían a los archivos cargados.

El propietario envió un reporte de S/ 10,00 y otro de S/ 5,00. El primero recibió una copia legible del comprobante y se aprobó por el importe verificado de S/ 12,00. El segundo se rechazó con un motivo. El cargo de la primera unidad quedó con S/ 38,00 pendientes. El historial conservó el original y la copia, y se pudo descargar cada versión desde ambos roles.

Una descarga sin firma respondió `403`. El segundo propietario recibió `404` al solicitar el estado de cuenta y la copia del comprobante de la unidad ajena. Su propia unidad conservó S/ 50,00 pendientes. El despliegue del frontend en Vercel y de la API en Render requiere una verificación posterior.

## Recorrido de identidad

Completar el arranque descrito en el [README](../README.md#desarrollo-local) y usar las dos cuentas de prueba.

1. Abrir `/admin` antes de iniciar sesión. Debe aparecer el formulario de acceso. Probar una contraseña incorrecta y luego entrar como SuperAdmin. Al recargar, el panel permanece abierto.
2. Cerrar sesión e intentar volver a `/admin`. Debe aparecer el formulario.
3. Entrar como Propietario y abrir `/admin`. El navegador vuelve a «Mis propiedades» y una solicitud a `/api/admin/session` devuelve `403`.
4. Comprobar el acceso con una sesión vencida mediante la [suite de API](../backend/tests/test_identity.py). También puede comprobarse en una base aislada fijando una fecha de vencimiento pasada en la sesión de prueba y recargando el panel. La aplicación debe volver al inicio de sesión.

## Recorrido de edificios

1. Entrar como SuperAdmin. En una base vacía, se muestra el listado vacío y el enlace «Nuevo edificio».
2. Registrar un edificio con capacidad y datos de pago ficticios. Abrir la ficha y confirmar que los campos de cuenta y CCI conservan sus ceros iniciales. Editar la capacidad, borrar un dato opcional y recargar la ficha para confirmar los cambios.
3. Volver al listado y abrir el edificio por nombre. Tras cerrar sesión y entrar como Propietario, abrir la dirección de la ficha. El navegador debe volver a «Mis propiedades» y la API debe devolver `403`.

## Recorrido de unidades y propietarios

1. Crear dos edificios con capacidad de una unidad. Abrir el padrón del primero y registrar una unidad con una cuenta de propietario nueva.
2. Registrar otra unidad en el segundo edificio seleccionando la cuenta anterior. Se puede usar el mismo número porque corresponde a otro edificio.
3. Editar el número y el área físicos de una unidad. Editar el nombre del propietario desde la otra y comprobar que el cambio se muestra en ambos edificios. Buscar por número, nombre o usuario.
4. Intentar reducir a cero la capacidad de un edificio ocupado. El sistema debe rechazar el cambio y conservar la capacidad registrada. Las [pruebas con PostgreSQL](../backend/tests/test_units.py) también ejecutan dos altas para la última plaza y un alta en paralelo con una reducción de capacidad. Solo una operación se confirma en cada caso.

## Recorrido de Mis propiedades

1. Entrar con una cuenta de propietario sin unidades. Comprobar el mensaje de lista vacía.
2. Desde administración, asignarle unidades en dos edificios. Asociar otra unidad del mismo edificio a un segundo propietario.
3. Volver a iniciar sesión con la primera cuenta. Abrir cada grupo de «Mis propiedades» y comprobar su unidad, área, edificio, dirección e instrucciones de pago. Si el edificio aún no tiene instrucciones configuradas, la ficha lo indica.
4. Abrir la dirección de la unidad ajena. El portal muestra «No se encontró la unidad» y la API responde `404`. Al iniciar sesión como el segundo propietario, este puede abrir su propia ficha.

## Recorrido del catálogo de servicios

1. Como SuperAdmin, abrir «Servicios» desde la ficha de un edificio. Comprobar el mensaje de catálogo vacío.
2. Crear un servicio lineal y uno por consumo medido. Recargar y comprobar el nombre y tipo de reparto de ambos.
3. Intentar registrar el mismo nombre cambiando las mayúsculas. El catálogo rechaza el duplicado. Abrir otro edificio y comprobar que su catálogo admite ese nombre.
4. Iniciar sesión como Propietario. Las rutas de consulta y alta del catálogo administrativo devuelven `403`.

## Recorrido de facturación lineal

1. Como SuperAdmin, abrir «Facturas» en un edificio con las unidades 001, 002 y 003 y un servicio lineal.
2. Registrar una factura de S/ 100,00. Su ficha debe mostrar S/ 33,34 para 001 y S/ 33,33 para cada una de las otras unidades. Recargar y comprobar el mismo desglose.
3. Volver al historial e intentar registrar otra factura del mismo servicio y periodo. La API devuelve `409` y el historial conserva una sola factura para ese periodo.
4. En [las pruebas de integración](../backend/tests/test_linear_invoices.py), verificar el estado persistido ante dos altas simultáneas y ante un fallo al guardar los cargos. El fallo revierte tanto la factura como sus cargos.

## Recorrido de facturación por consumo medido

1. Seleccionar un servicio medido, mes y año para cargar una lectura por unidad. En un periodo sin historial se puede indicar la lectura anterior.
2. Intentar guardar consumos individuales de 60,000 m³ para dos unidades con un volumen de factura de 100,000 m³. La API debe rechazar la factura y conservar el historial sin cambios.
3. Registrar S/ 100,00 por 30,000 m³, con consumos propios de 10,000 y 5,000 m³. El volumen común es 15,000 m³ y los cargos son S/ 58,33 y S/ 41,67.
4. Abrir el periodo siguiente y comprobar que se precarga la lectura anterior del servicio correcto. Una lectura actual menor exige confirmar la vuelta a cero. Al abrir la ficha, se muestran la lectura anterior, la actual y el desglose de consumos.

## Recorrido de corrección de facturas

1. Abrir la ficha de una factura lineal con tres unidades, elegir «Corregir factura» y guardar S/ 100,01 con un motivo. Los cargos suman exactamente S/ 100,01. La ficha conserva sus adjuntos y muestra el motivo en «Correcciones».
2. Abrir la misma factura en dos pestañas. Guardar un cambio en una y luego intentar guardar en la otra. La API devuelve `409` a la segunda. Recargar la ficha y comprobar que muestra la corrección que se guardó.
3. En una factura medida con un periodo posterior registrado, intentar cambiar una lectura final que se usa en la siguiente factura. La API rechaza el cambio. Corregir el monto o un volumen que cubra el consumo y comprobar que se actualiza el reparto.
4. La [suite con PostgreSQL](../backend/tests/test_invoice_corrections.py) comprueba que una factura marcada con movimientos conserva sus cargos y su historial ante un intento de edición directa.

## Recorrido de registro de pagos

1. Registrar dos facturas de S/ 50,00 para una misma unidad en diciembre y enero. Como SuperAdmin, abrir la unidad y elegir «Estado de cuenta». Debe mostrar S/ 100,00 pendientes.
2. Registrar S/ 10,00 con fecha de recepción y enero como mes de aplicación. Deben quedar S/ 90,00 pendientes. Al abrir el detalle del pago se ve una aplicación de S/ 10,00 al cargo de diciembre. El periodo indicado queda como referencia del pago.
3. Registrar S/ 95,00 con el mismo mes de aplicación. El detalle muestra S/ 40,00 aplicados a diciembre y S/ 50,00 a enero, con S/ 5,00 de crédito. Repetir con la misma clave de solicitud debe conservar un solo pago de S/ 95,00.
4. Iniciar sesión como Propietario y entrar al estado de cuenta de la unidad. Comprobar el filtro de periodo, el crédito y el detalle de las aplicaciones. Una unidad ajena devuelve `404`. El [contrato y los efectos persistidos](../backend/tests/test_collections.py) se comprueban con PostgreSQL.

## Recorrido de reportes de pago

1. Como Propietario, enviar un reporte con un PDF desde el estado de cuenta. Debe aparecer como «Pendiente de revisión» y el total pendiente conserva su importe.
2. Como SuperAdmin, abrir «Reportes de pago» desde el edificio y descargar el comprobante. Aprobar indicando el importe efectivamente recibido. Al repetir la misma aprobación, el estado de cuenta debe mostrar un solo pago.
3. Enviar otro reporte y rechazarlo con un motivo. El propietario debe ver el motivo en su historial y la deuda debe reflejar solo el pago aprobado.
4. Las [pruebas de API](../backend/tests/test_collections.py) verifican acceso por titular y edificio, formatos, tamaño, reintento tras error de almacenamiento y enlace temporal. El recorrido local usa un adaptador de prueba. La validación con el bucket está en la [guía de S3](archivos-s3.md).

## Recorrido de reemplazo de comprobantes

1. En un reporte pendiente, descargar el original y guardar una copia nueva con un motivo. Abrir de nuevo el reporte. El historial debe mostrar el original, la copia vigente, la cuenta y la fecha de cada carga, junto con el motivo del reemplazo.
2. Descargar ambas versiones y comprobar que cada una corresponde a su archivo. Iniciar sesión como el propietario que envió el reporte y comprobar el mismo historial.
3. Abrir el reporte en dos sesiones. Reemplazar el archivo desde una e intentar aprobar desde la otra. La API debe devolver `409` y pedir actualizar el reporte.
4. Actualizar la bandeja, revisar la versión vigente y aprobar. El pago se aplica una sola vez y el historial del comprobante sigue disponible. Las [pruebas de integración](../backend/tests/test_collections.py) también verifican permisos, reintentos y recuperación tras un error de almacenamiento.

## Recorrido de crédito automático y arrastres

El 17 de noviembre de 2026 comprobé este cambio con PostgreSQL 17 aislado. La suite completa pasó con 98 pruebas. Ruff, formato, TypeScript, compilación y `alembic check` forman parte de la validación local. La prueba de migración crea un esquema independiente en la revisión 0011 con un pago, crédito y aplicación existentes, comprueba su conservación al subir a 0012 y verifica la protección del rollback con arrastres.

Las pruebas concurrentes ejecutan emisión y pago sobre el mismo crédito, dos facturas de servicios distintos para el mismo periodo y dos confirmaciones del mismo pago. Comprueban los saldos persistidos y la unicidad de aplicaciones y arrastres. Otro caso fuerza un fallo después de conciliar y comprueba que la factura, el crédito y las constancias se revierten juntos.

El recorrido de navegador usó una API, un frontend y una base de pruebas independientes, con datos ficticios. Como SuperAdmin abrí una unidad con dos cargos de S/ 50,00 y un pago de S/ 70,00. El segundo cargo recibió automáticamente S/ 20,00 de crédito y mostró S/ 30,00 pendientes. Abrí el detalle del pago con Enter y comprobé la aplicación, su fecha y la cuenta que registró la operación.

Como segundo propietario abrí su propia unidad. El saldo de diciembre de S/ 50,00 quedó vinculado a febrero, omitiendo enero sin factura. El pendiente total fue S/ 100,00 por sus dos cargos. Seleccioné febrero con teclado y comprobé el cargo del mes junto con la constancia del saldo anterior. En una vista de 390 píxeles los bloques se apilaron y el contenido no desbordó horizontalmente.

Para reproducir el flujo:

1. Aplicar `alembic upgrade head` a una base de pruebas y crear dos unidades de propietarios diferentes.
2. Emitir diciembre con S/ 50,00 por unidad. Registrar S/ 70,00 en una de ellas: quedan S/ 20,00 de crédito.
3. Emitir febrero, sin factura en enero. La primera unidad queda con S/ 30,00 pendientes y crédito cero. La otra conserva S/ 100,00 pendientes y un arrastre de S/ 50,00 desde diciembre.
4. Consultar ambos estados de cuenta con sus propietarios. Cada uno debe ver solamente su unidad. En el filtro mensual, los pagos anteriores con aplicaciones al mes también quedan disponibles para consultar su detalle.
5. Registrar un pago sobre el saldo arrastrado. La constancia conserva el importe histórico y muestra el pendiente actual del cargo. La factura de origen sigue bloqueada para correcciones directas.

La conciliación y la protección entre dos propietarios también se verifican en API. La migración `0012_automatic_credit_and_carry` se aplicó a la base de demostración en Neon el 17 de noviembre de 2026. `alembic check` confirmó la correspondencia del esquema con los modelos. La base quedó con 17 tablas. La comparación de huellas antes y después conservó los registros de siete tablas financieras y comprobó la fecha y el responsable de las aplicaciones anteriores. El recorrido de interfaz de esta entrega usó PostgreSQL aislado; queda por repetirlo con Neon y comprobar el despliegue en Vercel y Render. Los objetos de S3 no se modificaron.

## Recorrido de ajustes auditados

El 17 de noviembre de 2026 verifiqué los ajustes con PostgreSQL 17 aislado y datos ficticios. Las pruebas de API cubren aumentos, reducciones a cero, pagos parciales, reintentos, revisiones antiguas, edificios ajenos y consultas de dos propietarios. Un cargo pagado de S/ 100,00 corregido a S/ 80,00 conserva su pago y genera S/ 20,00 de crédito. Si hay otros cargos pendientes de la unidad, ese dinero se aplica automáticamente.

La suite también comprueba reducciones y aumentos sucesivos sobre la misma aplicación, la conservación de lecturas y arrastres, y el rollback ante un fallo después de conciliar. Las pruebas concurrentes ejecutan dos ajustes iguales, dos revisiones en conflicto y un ajuste simultáneo a un pago. La prueba de migración conserva los valores de una aplicación existente al asignarle identidad y verifica la protección del descenso con historial de ajustes y liberaciones.

Desde el navegador entré como SuperAdmin, abrí una factura de S/ 200,00 para dos unidades y ajusté el cargo pagado de la primera de S/ 100,00 a S/ 80,00, indicando el motivo. Guardé con teclado y comprobé el historial y el total vigente de S/ 180,00. Después registré S/ 95,00 como nuevo importe: la factura conservó S/ 200,00 originales, el total vigente pasó a S/ 195,00 y el foco llegó al aviso de confirmación.

Como propietario de la primera unidad, consulté S/ 95,00 aplicados y S/ 5,00 de crédito disponible. El detalle conservó la aplicación inicial de S/ 100,00, su liberación de S/ 20,00 y una nueva aplicación automática de S/ 15,00. El historial mostró los dos ajustes con su motivo, fecha y responsable. El formulario a 390 píxeles conservó sus controles, el foco visible y el contenido sin desbordamiento horizontal.

Para reproducir:

1. Aplicar `alembic upgrade head` en una base de pruebas. Emitir S/ 100,00 para una unidad y registrar un pago exacto.
2. Abrir la factura como SuperAdmin. Registrar S/ 80,00 y un motivo desde «Ajustar un cargo». Verificar S/ 20,00 de crédito y el cargo original de S/ 100,00.
3. Registrar S/ 95,00 como nuevo importe. Verificar otra entrada de historial, una nueva aplicación de S/ 15,00 y S/ 5,00 de crédito.
4. Entrar como propietario y consultar el estado de cuenta. Comprobar que otro propietario no accede a la unidad ni a sus ajustes.
5. En dos sesiones administrativas, intentar ajustar la misma revisión. Una operación se confirma y la otra pide actualizar la ficha. Reintentar la misma solicitud conserva un solo ajuste.

La suite completa pasó con 112 pruebas en PostgreSQL 17 aislado. Ruff, formato, TypeScript, compilación y `alembic check` fueron correctos. La migración 0013, los ajustes y sus liberaciones se verificaron localmente. Esta entrega no modificó Neon ni S3, ni ejecutó un despliegue o CI remoto.
