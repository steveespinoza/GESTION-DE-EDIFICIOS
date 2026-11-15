# Gestión de Edificios

Aplicación para administrar edificios residenciales, repartir gastos de servicios y consultar estados de cuenta. La administración registra facturas, valida pagos, atiende incidencias y lleva el historial de mantenimiento. Cada propietario puede consultar las unidades asociadas a su cuenta y reportar pagos hechos por un canal externo.

Este proyecto parte de un sistema de gestión inmobiliaria que desarrollé anteriormente. Desde «Edificios», el SuperAdmin configura la capacidad y las instrucciones de pago, administra el padrón y registra servicios con reparto lineal o por consumo medido. Una misma cuenta de propietario puede tener unidades en varios edificios. En «Mis propiedades», el propietario consulta sus unidades y las instrucciones de pago. La emisión de cargos, los saldos y los estados de cuenta se incorporarán con la facturación y las cobranzas.

## Arquitectura

El frontend usa React y TypeScript. La API usa FastAPI y crecerá como un monolito modular con SQLAlchemy, PostgreSQL y Alembic. Los comprobantes, las evidencias y los recibos se guardarán en S3 cuando se implementen esos flujos.

## Desarrollo local

Necesitas Git, Python 3.13, `uv`, Node.js 22.12 o superior y Docker con el complemento Compose. Desde la raíz del repositorio, levanta la base local.

```sh
docker compose up -d --wait postgres
```

En una terminal, prepara y ejecuta el backend.

```sh
cd backend
cp .env.example .env
uv sync --locked
uv run --locked --env-file .env alembic upgrade head
uv run --locked --env-file .env python -m app.identity.seed_demo
uv run --locked --env-file .env uvicorn app.main:app --reload
```

En PowerShell puedes copiar el archivo con `Copy-Item .env.example .env`. La variable `DATABASE_URL` es la conexión que usa Alembic. Si ya tienes una instancia local de PostgreSQL, configura esa variable para una base de desarrollo y omite el contenedor.

En otra terminal, desde la raíz, inicia el frontend.

```sh
cd frontend
npm ci
npm run dev
```

Abre [el formulario de acceso](http://localhost:5173). El comando de datos de prueba crea `admin.demo` y `propietario.demo` y muestra sus contraseñas aleatorias al crearlas. Si se vuelve a ejecutar, conserva las cuentas existentes. Usa esas cuentas en una base local de desarrollo.

La [ruta de salud](http://127.0.0.1:8000/api/health) responde `{"status":"ok"}` cuando la API está activa. La sesión usa una cookie `HttpOnly` y vence a las ocho horas. El archivo de ejemplo desactiva `Secure` para desarrollo por HTTP. Para el despliegue, conserva el valor seguro predeterminado y sirve el frontend y `/api` bajo el mismo origen HTTPS.

## Comprobaciones

Desde `backend/`:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked --env-file .env alembic check
```

Para ejecutar las pruebas de integración, apunta `TEST_DATABASE_URL` a una base PostgreSQL de pruebas con las migraciones aplicadas. Puedes definir esa variable en un archivo de entorno local y pasarlo a `uv run --locked --env-file ARCHIVO pytest`. La suite elimina sus datos de prueba y GitHub Actions levanta su propia base.

Desde `frontend/`:

```sh
npm run build
```

GitHub Actions ejecuta estas comprobaciones en los PR. Las migraciones crean los roles, las cuentas, las sesiones, los edificios, las unidades y los catálogos de servicios.

## Documentación

| Documento | Contenido |
| --- | --- |
| [Requerimientos](docs/requerimientos.md) | Alcance, permisos, requisitos funcionales y condiciones de calidad. |
| [Casos de uso](docs/casos-de-uso.md) | Acciones de cada rol, resultados esperados y situaciones de error. |
| [Arquitectura](docs/arquitectura.md) | Módulos, dependencias, despliegue objetivo y modelo de datos conceptual. |
| [Facturación y cobranza](docs/facturacion-y-cobranza.md) | Reglas de cálculo, movimientos y secuencia desde la factura hasta el pago. |
| [Verificación](docs/verificacion.md) | Escenarios de aceptación, casos contables y rutas de prueba. |
| [Paridad funcional](docs/paridad.md) | Seguimiento de las capacidades que pasan a la nueva versión. |
