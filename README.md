# Gestión de Edificios

Aplicación para administrar edificios residenciales, repartir gastos de servicios y consultar estados de cuenta. La administración registra facturas, valida pagos, atiende incidencias y lleva el historial de mantenimiento. Cada propietario puede consultar las unidades asociadas a su cuenta y reportar pagos hechos por un canal externo.

Este proyecto parte de un sistema de gestión inmobiliaria que desarrollé anteriormente. En esta versión estoy definiendo el alcance y los casos de uso antes de implementar la aplicación. La prioridad es conservar los flujos completos y poder verificar cómo se calculan y cambian los saldos.

## Diseño previsto

El frontend usará React y TypeScript. La API se organizará como un monolito modular con FastAPI, SQLAlchemy y PostgreSQL. Los comprobantes, las evidencias y los recibos se guardarán en S3.

## Documentación

| Documento | Contenido |
| --- | --- |
| [Requerimientos](docs/requerimientos.md) | Alcance, permisos, requisitos funcionales y condiciones de calidad. |
| [Casos de uso](docs/casos-de-uso.md) | Acciones de cada rol, resultados esperados y situaciones de error. |
| [Arquitectura](docs/arquitectura.md) | Módulos, dependencias, despliegue objetivo y modelo de datos conceptual. |
| [Facturación y cobranza](docs/facturacion-y-cobranza.md) | Reglas de cálculo, movimientos y secuencia desde la factura hasta el pago. |
| [Verificación](docs/verificacion.md) | Escenarios de aceptación, casos contables y rutas de prueba. |
| [Paridad funcional](docs/paridad.md) | Seguimiento de las capacidades que pasan a la nueva versión. |
