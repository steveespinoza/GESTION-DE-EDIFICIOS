from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.identity.models import Account, RoleName
from app.properties.models import Building, Unit
from app.properties.schemas import BuildingInput
from app.properties.service import PropertyConflict, count_units, replace_building
from app.properties.unit_schemas import UnitCreate
from app.properties.unit_service import create_unit

BUILDINGS = "/api/admin/buildings"
OWNERS = "/api/admin/owners"


def building(admin, session_header, name="Edificio de prueba", capacity=3):
    response = admin.post(
        BUILDINGS, json={"name": name, "total_units": capacity}, headers=session_header
    )
    assert response.status_code == 201
    return response.json()["id"]


def existing_owner(owner_id, number="001"):
    return {
        "number": number,
        "area_sqm": "42.25",
        "owner": {"kind": "existing", "id": str(owner_id)},
    }


def new_owner(username="propietaria.nueva", number="001"):
    return {
        "number": number,
        "area_sqm": "60.50",
        "owner": {
            "kind": "new",
            "full_name": "Ana de Prueba",
            "username": username,
            "email": "ana@example.com",
            "phone": "000 123 456",
            "password": "initial-test-password",
        },
    }


def test_creates_owner_and_reuses_the_account_across_buildings(
    admin, session_header, sign_in
):
    first = f"{BUILDINGS}/{building(admin, session_header, 'Primero')}/units"
    second = f"{BUILDINGS}/{building(admin, session_header, 'Segundo')}/units"

    created = admin.post(first, json=new_owner(), headers=session_header)
    assert created.status_code == 201
    first_unit = created.json()
    assert first_unit["number"] == "001"
    assert first_unit["area_sqm"] == "60.50"
    assert first_unit["owner"]["phone"] == "000 123 456"
    assert set(first_unit["owner"]) == {"id", "full_name", "username", "email", "phone"}
    owner_id = first_unit["owner"]["id"]
    assert any(row["id"] == owner_id for row in admin.get(OWNERS).json())

    reused = admin.post(second, json=existing_owner(owner_id), headers=session_header)
    assert reused.status_code == 201
    assert reused.json()["owner"]["id"] == owner_id

    first_detail = f"{first}/{first_unit['id']}"
    second_detail = f"{second}/{reused.json()['id']}"
    physically_updated = admin.put(
        first_detail,
        json={"number": "A-101", "area_sqm": "55.20"},
        headers=session_header,
    )
    assert physically_updated.status_code == 200
    result = admin.put(
        f"{first_detail}/owner",
        json={
            "full_name": "Ana Actualizada",
            "username": "ana.actualizada",
            "phone": None,
        },
        headers=session_header,
    )
    assert result.status_code == 200
    assert admin.get(first_detail).json()["number"] == "A-101"
    assert admin.get(first_detail).json()["area_sqm"] == "55.20"
    assert admin.get(second_detail).json()["owner"]["full_name"] == "Ana Actualizada"
    assert admin.get(second_detail).json()["owner"]["email"] is None

    for term in ("a-101", "actualizada", "ANA.ACTUALIZADA"):
        assert len(admin.get(first, params={"q": term}).json()) == 1
    assert admin.get(first, params={"q": "%"}).json() == []
    assert (
        sign_in("ana.actualizada", "initial-test-password").json()["role"]
        == "Propietario"
    )
    assert admin.get(first).status_code == 403
    assert admin.get(OWNERS).status_code == 403


def test_duplicate_rolls_back_new_owner_and_unit_changes(admin, session_header):
    units = f"{BUILDINGS}/{building(admin, session_header)}/units"
    owner_id = admin.get(OWNERS).json()[0]["id"]
    first = admin.post(units, json=existing_owner(owner_id), headers=session_header)
    second = admin.post(
        units, json=existing_owner(owner_id, "002"), headers=session_header
    )
    assert first.status_code == second.status_code == 201

    duplicated = admin.post(units, json=new_owner(), headers=session_header)
    assert duplicated.status_code == 409
    assert all(
        owner["username"] != "propietaria.nueva" for owner in admin.get(OWNERS).json()
    )
    second_path = f"{units}/{second.json()['id']}"
    assert (
        admin.put(
            second_path,
            json={"number": "001", "area_sqm": "50"},
            headers=session_header,
        ).status_code
        == 409
    )
    assert admin.get(second_path).json()["number"] == "002"
    assert len(admin.get(units).json()) == 2


def test_capacity_and_building_scope(admin, session_header):
    primary = f"{BUILDINGS}/{building(admin, session_header, capacity=1)}"
    other = f"{BUILDINGS}/{building(admin, session_header)}"
    units = f"{primary}/units"
    owner_id = admin.get(OWNERS).json()[0]["id"]
    first = admin.post(units, json=existing_owner(owner_id), headers=session_header)
    assert first.status_code == 201
    assert (
        admin.post(
            units, json=existing_owner(owner_id, "002"), headers=session_header
        ).status_code
        == 409
    )
    assert (
        admin.put(
            primary, json={"name": "Otro", "total_units": 0}, headers=session_header
        ).status_code
        == 409
    )
    assert admin.get(primary).json()["total_units"] == 1
    assert admin.get(primary).json()["name"] == "Edificio de prueba"
    foreign_unit = f"{other}/units/{first.json()['id']}"
    assert admin.get(foreign_unit).status_code == 404
    assert (
        admin.put(
            foreign_unit,
            json={"number": "101", "area_sqm": "3"},
            headers=session_header,
        ).status_code
        == 404
    )


def test_inactive_owner_and_invalid_area_are_rejected(admin, session_header, sessions):
    units = f"{BUILDINGS}/{building(admin, session_header)}/units"
    with sessions() as db:
        inactive_id = db.scalar(
            select(Account.id).where(Account.username == "test-inactive")
        )
    assert (
        admin.post(
            units, json=existing_owner(inactive_id), headers=session_header
        ).status_code
        == 409
    )
    assert (
        admin.post(
            units, json=new_owner() | {"area_sqm": "10.123"}, headers=session_header
        ).status_code
        == 422
    )
    assert admin.get(units).json() == []


def test_owner_username_and_email_conflicts_leave_the_unit_unregistered(
    admin, session_header
):
    units = f"{BUILDINGS}/{building(admin, session_header)}/units"
    assert (
        admin.post(units, json=new_owner(), headers=session_header).status_code == 201
    )

    same_username = new_owner(number="002")
    same_username["owner"]["email"] = "distinto@example.com"
    response = admin.post(units, json=same_username, headers=session_header)
    assert response.status_code == 409
    assert response.json()["detail"] == "El nombre de usuario ya está registrado."

    same_email = new_owner(username="otra.persona", number="003")
    response = admin.post(units, json=same_email, headers=session_header)
    assert response.status_code == 409
    assert response.json()["detail"] == "El correo electrónico ya está registrado."
    assert [unit["number"] for unit in admin.get(units).json()] == ["001"]


@pytest.fixture
def committed_workspace(engine, test_password_hash):
    building_id, owner_id = uuid4(), uuid4()
    with Session(engine) as db, db.begin():
        db.add(
            Account(
                id=owner_id,
                username=f"race-{owner_id}",
                full_name="Cuenta de concurrencia",
                role_name=RoleName.OWNER.value,
                password_hash=test_password_hash,
            )
        )
        db.add(Building(id=building_id, name="Edificio de concurrencia", total_units=1))
    try:
        yield building_id, owner_id
    finally:
        with Session(engine) as db, db.begin():
            db.execute(delete(Unit).where(Unit.building_id == building_id))
            db.execute(delete(Building).where(Building.id == building_id))
            db.execute(delete(Account).where(Account.id == owner_id))


@pytest.mark.parametrize("second_operation", ["add", "reduce"])
def test_concurrent_operations_cannot_exceed_capacity(
    engine, committed_workspace, second_operation
):
    building_id, owner_id = committed_workspace
    barrier = Barrier(2)

    def execute(operation, number):
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            try:
                if operation == "add":
                    create_unit(
                        db,
                        building_id,
                        UnitCreate.model_validate(existing_owner(owner_id, number)),
                    )
                else:
                    replace_building(
                        db,
                        building_id,
                        BuildingInput(name="Edificio de concurrencia", total_units=0),
                    )
            except PropertyConflict:
                return False
            return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(execute, "add", "1")
        second = executor.submit(execute, second_operation, "2")
        assert sorted([first.result(timeout=15), second.result(timeout=15)]) == [
            False,
            True,
        ]
    with Session(engine) as db:
        persisted = db.get(Building, building_id)
        assert persisted is not None
        assert count_units(db, building_id) == persisted.total_units
