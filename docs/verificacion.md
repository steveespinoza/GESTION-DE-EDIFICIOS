# Verificación

La verificación empieza con datos ficticios de dos edificios. Un propietario tiene una unidad en cada edificio y otro tiene una sola unidad. El SuperAdmin puede administrar ambos. Esta distribución permite comprobar el alcance de consultas, pagos, documentos y adjuntos.

## Escenarios de aceptación previstos

| Prueba | Requisitos | Resultado esperado |
| --- | --- | --- |
| Sesión | IDE-01 | Cada rol llega a su panel. El cierre o vencimiento de sesión retira el acceso y la API rechaza el acceso con el rol equivocado. |
| Perfil | IDE-02 | Una contraseña de confirmación incorrecta conserva los datos anteriores. |
| Alta simultánea de unidades | EDI-01, UNI-01, UNI-02 | Con una plaza disponible, una sola alta se confirma. El número se mantiene único por edificio y la búsqueda encuentra la ficha por unidad o propietario. |
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
