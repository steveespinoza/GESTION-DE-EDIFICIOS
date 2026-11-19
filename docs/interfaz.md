# Organización de la interfaz

Retomé la organización visual del sistema anterior para dar continuidad al recorrido: barra lateral azul, contexto del edificio, panel de módulos y tablas compactas. La aplicación conserva su identidad «Gestión de Edificios» y utiliza iconos SVG propios.

La paleta usa azul `#264b82`, azul oscuro `#1b355c`, fondo `#f8fafc`, bordes claros y esquinas de 4 px. La tipografía Plus Jakarta Sans se sirve desde el mismo frontend; su licencia SIL Open Font License está incluida en `frontend/public/fonts/OFL-PlusJakartaSans.txt`.

- **Administración:** el listado abre el panel del edificio, con accesos a unidades, servicios, facturas y consumos, reportes de pago, cobranzas y recibos por lote. La barra lateral mantiene el edificio seleccionado y señala el módulo activo.
- **Propietarios:** la navegación muestra Mis propiedades y, dentro de una unidad, Mi unidad y Estado de cuenta y recibos. El nombre del contexto procede de las consultas protegidas existentes.
- **Cobranzas:** el resumen mantiene el pendiente global y el vencido. Los registros se agrupan por periodo en tablas desplegables; el periodo más reciente se abre primero. Las descargas se reúnen en «Reportes y exportaciones» y el formulario de fechas en «Configurar vencimientos».
- **Unidades y facturas:** los listados usan tablas. El alta de una factura se abre desde «Registrar factura o consumo».
- **Acceso y móvil:** el inicio de sesión tiene una presentación lateral en escritorio y una sola columna en móvil. Por debajo de 1024 px, la navegación se abre en un diálogo; Escape, cerrar y elegir un destino lo cierran. Las tablas anchas tienen desplazamiento propio.

Los cambios presentan las respuestas existentes de la API. No alteran las reglas de reparto, pagos, crédito, vencimientos, emisión o permisos. La entrega no requiere migración ni nuevas dependencias de ejecución.

El [recorrido de verificación](verificacion.md#recorrido-de-la-interfaz-reorganizada) contiene capturas y los límites de la comprobación local.
