import os
from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
    Security,
    status,
)
from fastapi.security import APIKeyCookie

from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.schemas import LoginRequest, SessionUser
from app.identity.service import (
    SESSION_LIFETIME,
    end_session,
    find_session,
    start_session,
)

router = APIRouter(prefix="/api", tags=["Identidad"])
SESSION_COOKIE = "edificios_session"
SessionCookie = Annotated[
    str | None, Security(APIKeyCookie(name=SESSION_COOKIE, auto_error=False))
]


def require_session_header(
    marker: Annotated[str | None, Header(alias="X-Edificios-Request")] = None,
) -> None:
    if marker != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Solicitud no permitida."
        )


def secure_cookie() -> bool:
    return os.environ.get("SESSION_COOKIE_SECURE") != "false"


def get_current_user(
    db: RequestSession, token: SessionCookie, response: Response
) -> SessionUser:
    user = find_session(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida."
        )
    response.headers["Cache-Control"] = "no-store"
    return user


CurrentUser = Annotated[SessionUser, Depends(get_current_user)]


def require_role(role: RoleName) -> Callable[[SessionUser], SessionUser]:
    def authorize(user: CurrentUser) -> SessionUser:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu cuenta no tiene acceso a esta sección.",
            )
        return user

    return authorize


@router.post("/auth/login", dependencies=[Depends(require_session_header)])
def login(data: LoginRequest, db: RequestSession, response: Response) -> SessionUser:
    session = start_session(db, data.username, data.password.get_secret_value())
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=secure_cookie(),
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return session.user


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_session_header)],
)
def logout(db: RequestSession, token: SessionCookie, response: Response) -> None:
    end_session(db, token)
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=secure_cookie(), samesite="strict"
    )
    response.headers["Cache-Control"] = "no-store"


@router.get("/auth/me")
def read_session(user: CurrentUser) -> SessionUser:
    return user


@router.get("/admin/session")
def read_admin_session(
    user: Annotated[SessionUser, Depends(require_role(RoleName.SUPERADMIN))],
) -> SessionUser:
    return user


@router.get("/owner/session")
def read_owner_session(
    user: Annotated[SessionUser, Depends(require_role(RoleName.OWNER))],
) -> SessionUser:
    return user
