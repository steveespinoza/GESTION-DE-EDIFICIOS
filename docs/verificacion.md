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
