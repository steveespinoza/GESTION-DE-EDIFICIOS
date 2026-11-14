import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.database import Base
from app.identity import models  # noqa: F401 -- Registers identity tables in Base.metadata.


def run_migrations() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run Alembic.")

    if context.is_offline_mode():
        context.configure(
            url=database_url,
            target_metadata=Base.metadata,
            literal_binds=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run_migrations()
