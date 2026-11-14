import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def configured_engine() -> Engine | None:
    url = os.environ.get("DATABASE_URL")
    return create_engine(url, pool_pre_ping=True) if url else None
