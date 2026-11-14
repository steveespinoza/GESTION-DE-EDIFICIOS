from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, SecretStr

from app.identity.models import RoleName


class LoginRequest(BaseModel):
    username: str
    password: SecretStr


class SessionUser(BaseModel):
    id: UUID
    username: str
    full_name: str
    role: RoleName
    expires_at: datetime
