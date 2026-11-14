from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from app.database import configured_engine
from app.identity.router import router as identity_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = configured_engine()
    app.state.sessions = sessionmaker(bind=engine) if engine is not None else None
    try:
        yield
    finally:
        if engine is not None:
            engine.dispose()


app = FastAPI(title="Gestión de Edificios", version="0.1.0", lifespan=lifespan)
app.include_router(identity_router)


@app.exception_handler(RequestValidationError)
async def validation_error(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    details = [
        {key: issue[key] for key in ("loc", "msg", "type")} for issue in error.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": details},
    )


class HealthResponse(BaseModel):
    status: Literal["ok"]


@app.get("/api/health", tags=["Operación"])
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok")
