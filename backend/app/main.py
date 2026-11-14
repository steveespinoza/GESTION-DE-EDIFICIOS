from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Gestión de Edificios", version="0.1.0")


class HealthResponse(BaseModel):
    status: Literal["ok"]


@app.get("/api/health", tags=["Operación"])
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok")
