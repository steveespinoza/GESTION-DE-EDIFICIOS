import secrets

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import configured_engine
from app.identity.models import Account, RoleName
from app.identity.service import password_hash

DEMO_ACCOUNTS = (
    ("admin.demo", "SuperAdmin de prueba", RoleName.SUPERADMIN),
    ("propietario.demo", "Propietario de prueba", RoleName.OWNER),
)


def main() -> None:
    engine = configured_engine()
    if engine is None:
        raise SystemExit("Configura DATABASE_URL antes de crear cuentas de prueba.")

    created: list[tuple[str, str]] = []
    try:
        with Session(engine) as db, db.begin():
            for username, full_name, role in DEMO_ACCOUNTS:
                password = secrets.token_urlsafe(18)
                statement = (
                    insert(Account)
                    .values(
                        username=username,
                        full_name=full_name,
                        role_name=role.value,
                        password_hash=password_hash.hash(password),
                    )
                    .on_conflict_do_nothing(index_elements=[Account.username])
                    .returning(Account.username)
                )
                if db.scalar(statement) is not None:
                    created.append((username, password))
    finally:
        engine.dispose()

    if not created:
        print("Las cuentas de prueba ya existen. Se conservaron sus contraseñas.")
    for username, password in created:
        print(f"{username}  {password}")


if __name__ == "__main__":
    main()
