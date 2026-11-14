from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker


def get_db(request: Request) -> Iterator[Session]:
    sessions: sessionmaker[Session] | None = request.app.state.sessions
    if sessions is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La conexión de la aplicación no está configurada.",
        )
    with sessions() as db:
        yield db


RequestSession = Annotated[Session, Depends(get_db)]
