# Gestión de Edificios

Aplicación para administrar edificios residenciales, repartir gastos de servicios y consultar estados de cuenta. La administración registra facturas, valida pagos, atiende incidencias y lleva el historial de mantenimiento. Cada propietario puede consultar las unidades asociadas a su cuenta y reportar pagos hechos por un canal externo.

Este proyecto parte de un sistema de gestión inmobiliaria que desarrollé anteriormente. La base incluye el frontend, la API y la configuración local de PostgreSQL. El primer flujo de negocio previsto es el acceso de SuperAdmin y Propietario.

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
uv run --locked uvicorn app.main:app --reload
```

En PowerShell puedes copiar el archivo con `Copy-Item .env.example .env`. La variable `DATABASE_URL` es la conexión que usa Alembic. Si ya tienes una instancia local de PostgreSQL, configura esa variable para una base de desarrollo y omite el contenedor.

En otra terminal, desde la raíz, inicia el frontend.

```sh
cd frontend
npm ci
npm run dev
```

Abre [el frontend](http://localhost:5173) para ver el estado de la API. La [ruta de salud](http://127.0.0.1:8000/api/health) responde `{"status":"ok"}` cuando la API está activa. La conexión y el esquema se verifican por separado con Alembic.

## Comprobaciones

Desde `backend/`:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked --env-file .env alembic check
```

Desde `frontend/`:

```sh
npm run build
```

GitHub Actions ejecuta estas comprobaciones en los PR. El entorno de migraciones está preparado para incorporar la primera tabla en el módulo de identidad.

## Documentación

| Documento | Contenido |
| --- | --- |
| [Requerimientos](docs/requerimientos.md) | Alcance, permisos, requisitos funcionales y condiciones de calidad. |
| [Casos de uso](docs/casos-de-uso.md) | Acciones de cada rol, resultados esperados y situaciones de error. |
| [Arquitectura](docs/arquitectura.md) | Módulos, dependencias, despliegue objetivo y modelo de datos conceptual. |
| [Facturación y cobranza](docs/facturacion-y-cobranza.md) | Reglas de cálculo, movimientos y secuencia desde la factura hasta el pago. |
| [Verificación](docs/verificacion.md) | Escenarios de aceptación, casos contables y rutas de prueba. |
| [Paridad funcional](docs/paridad.md) | Seguimiento de las capacidades que pasan a la nueva versión. |
