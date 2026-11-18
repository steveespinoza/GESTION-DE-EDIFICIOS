# Requerimientos

El sistema cubre la gestión de edificios residenciales desde el registro de la unidad hasta la consulta de sus cargos y pagos. El alcance de esta versión incluye dos roles, SuperAdmin y Propietario. Una sola cuenta de propietario puede estar vinculada a varias unidades en distintos edificios.

## Permisos

| Recurso | SuperAdmin | Propietario |
| --- | --- | --- |
| Cuenta | Inicia y cierra sesión. Actualiza los datos y restablece la contraseña de un propietario. | Inicia y cierra sesión. Actualiza su perfil y su contraseña. |
| Edificios y unidades | Consulta y administra los edificios y su padrón. | Consulta las unidades asociadas a su cuenta y la información de pago de sus edificios. |
| Facturación y cobranza | Registra facturas, revisa comprobantes, confirma pagos y consulta consolidados. | Consulta sus cargos y saldos, y reporta pagos con comprobante. |
| Documentos | Emite recibos individuales y por lote, y descarga los consolidados. | Descarga sus recibos y el informe de transparencia del edificio correspondiente. |
| Incidencias y mantenimiento | Atiende incidencias y administra el catálogo, historial y calendario de equipos. | Reporta incidencias de su unidad o de áreas comunes del edificio. |

## Requisitos funcionales

Los identificadores se comparten con la [matriz de paridad](paridad.md). Los [casos de uso](casos-de-uso.md) describen cómo se ejercen estos requisitos.

| ID | Requisito |
| --- | --- |
| IDE-01 | Autenticar por usuario y contraseña, abrir el panel según el rol y retirar el acceso al cerrar sesión o vencer la sesión. |
| IDE-02 | Permitir al propietario editar sus datos o cambiar la contraseña tras confirmar su clave vigente. Para restablecer la de un propietario, el SuperAdmin confirma su propia clave. |
| EDI-01 | Crear, consultar y editar edificios, incluida su capacidad y las instrucciones de pago. |
| UNI-01 | Registrar unidades con un propietario nuevo o existente. Aplicar la capacidad del edificio y la unicidad del identificador por edificio. |
| UNI-02 | Listar, buscar y consultar unidades con su propietario. Editar el área, el identificador y los datos del propietario. |
| FAC-01 | Mantener un catálogo de servicios por edificio con reparto lineal o por consumo medido. |
| FAC-02 | Registrar facturas con periodo, fechas, monto, volumen según el servicio, adjuntos y comprobante. Consultar el histórico, corregir facturas abiertas y registrar ajustes auditados por unidad en cargos con pagos o arrastres. |
| FAC-03 | Precargar la lectura anterior pertinente, admitir tres decimales, tratar reinicios de medidor y generar cargos que cuadren con el total facturado. |
| COB-01 | Reportar y revisar un comprobante de pago externo. Registrar o confirmar el pago con fecha y monto y mostrar su detalle en la cobranza del periodo. |
| COB-02 | Aplicar pagos exactos, parciales y excedentes. Aplicar automáticamente el crédito a los cargos de la misma unidad. Conservar el origen de los saldos y arrastres y evitar efectos duplicados. |
| POR-01 | Mostrar las propiedades asociadas a la cuenta, sus pendientes, instrucciones de pago y estados de cuenta por unidad y periodo. |
| DOC-01 | Emitir PDF por unidad y consolidado por edificio. Exportar Excel mensual, de transparencia y del histórico de cobranzas. |
| DOC-02 | Emitir y regenerar recibos por lote con fecha de vencimiento, versión y resultado por unidad. Permitir el reintento de fallos. |
| INC-01 | Reportar fallas en áreas comunes o unidades, con foto y ubicación opcionales. Consultar, filtrar, paginar y atender estos reportes desde administración. |
| MAN-01 | Registrar y editar equipos, proveedor y frecuencia. Consultar, registrar, editar y eliminar intervenciones con fecha, costo, proveedor y técnico. |
| MAN-02 | Mostrar la próxima intervención, el estado del equipo y el calendario mensual de eventos ejecutados y proyectados. |
| ARC-01 | Cargar y consultar facturas, comprobantes, fotos y recibos, con autorización sobre el recurso y acceso temporal a archivos privados. |

## Condiciones de calidad

| ID | Condición y forma de comprobarla |
| --- | --- |
| CAL-01 | La API valida el rol y la pertenencia del recurso. Una cuenta de prueba queda fuera de las unidades, archivos y reportes privados de otra. |
| CAL-02 | La suma de cargos coincide con la factura al céntimo. Pagos, créditos y arrastres se reconcilian en la API, los estados de cuenta y las exportaciones. |
| CAL-03 | Las restricciones de capacidad, unicidad y aprobación funcionan ante solicitudes simultáneas. La prueba comprueba el estado final en PostgreSQL. |
| CAL-04 | Los formularios y recorridos principales se pueden completar con teclado y en una pantalla estrecha. La interfaz muestra estados de carga, vacío y error. |
| CAL-05 | El entorno de demostración puede prepararse con migraciones y datos ficticios. La aplicación recibe credenciales por entorno y los errores conservan un identificador de solicitud sin registrar secretos. |

## Límites y decisiones pendientes

Los pagos se realizan fuera de la aplicación. La versión de portafolio usa datos ficticios y un entorno propio. La migración de registros empresariales queda fuera de esta entrega.

Queda por confirmar si existe un flujo que requiera un administrador restringido a un edificio o una cuenta de inquilino. Quedan por definir las columnas del Excel de transparencia. Los ajustes monetarios de cargos con movimientos conservan su origen y se registran por unidad. Los periodos sin facturas se omiten al registrar arrastres, conservando el periodo de origen.
