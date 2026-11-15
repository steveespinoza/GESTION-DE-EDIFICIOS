from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

BUILDINGS = "/api/admin/buildings"


def create_building(admin, session_header, name):
    response = admin.post(
        BUILDINGS, json={"name": name, "total_units": 5}, headers=session_header
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_catalog_lists_both_types_only_for_the_selected_building(admin, session_header):
    cedros = create_building(admin, session_header, "Cedros")
    alameda = create_building(admin, session_header, "Alameda")
    first = f"{BUILDINGS}/{cedros}/services"
    second = f"{BUILDINGS}/{alameda}/services"
    assert admin.get(first).json() == []

    fixed = admin.post(
        first,
        json={"name": "  Mantenimiento  ", "calculation_type": "LINEAR"},
        headers=session_header,
    )
    metered = admin.post(
        first,
        json={"name": "Agua", "calculation_type": "METERED"},
        headers=session_header,
    )
    assert fixed.status_code == metered.status_code == 201
    assert fixed.json()["name"] == "Mantenimiento"
    assert fixed.json()["building_id"] == metered.json()["building_id"] == cedros
    assert admin.get(first).json() == [metered.json(), fixed.json()]
    assert admin.get(second).json() == []

    same_name = admin.post(
        second,
        json={"name": "Agua", "calculation_type": "LINEAR"},
        headers=session_header,
    )
    assert same_name.status_code == 201
    assert admin.get(second).json() == [same_name.json()]
    assert admin.get(first).json() == [metered.json(), fixed.json()]


def test_duplicate_names_are_case_insensitive_and_confined_to_one_building(
    admin, session_header
):
    building_id = create_building(admin, session_header, "Cedros")
    endpoint = f"{BUILDINGS}/{building_id}/services"
    saved = admin.post(
        endpoint,
        json={"name": "Agua", "calculation_type": "METERED"},
        headers=session_header,
    )
    assert saved.status_code == 201
    duplicate = admin.post(
        endpoint,
        json={"name": "  aGUA ", "calculation_type": "LINEAR"},
        headers=session_header,
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Ya existe un servicio con ese nombre en este edificio."
    }
    assert admin.get(endpoint).json() == [saved.json()]


@pytest.mark.parametrize(
    "data",
    [
        {"name": "  ", "calculation_type": "LINEAR"},
        {"name": "Agua", "calculation_type": "OTHER"},
        {"name": "Agua", "calculation_type": "LINEAR", "building_id": str(uuid4())},
    ],
)
def test_invalid_creation_leaves_the_catalog_unchanged(admin, session_header, data):
    building_id = create_building(admin, session_header, "Cedros")
    endpoint = f"{BUILDINGS}/{building_id}/services"
    assert admin.post(endpoint, json=data, headers=session_header).status_code == 422
    assert admin.get(endpoint).json() == []


def test_catalog_requires_an_existing_building_and_request_header(
    admin, session_header
):
    missing = f"{BUILDINGS}/{uuid4()}/services"
    data = {"name": "Agua", "calculation_type": "METERED"}
    assert admin.get(missing).status_code == 404
    assert admin.post(missing, json=data, headers=session_header).status_code == 404
    building = create_building(admin, session_header, "Cedros")
    endpoint = f"{BUILDINGS}/{building}/services"
    assert admin.post(endpoint, json=data).status_code == 403
    assert admin.get(endpoint).json() == []


def test_catalog_can_only_be_accessed_by_superadmin(client, sign_in, session_header):
    assert sign_in("test-admin").status_code == 200
    building = create_building(client, session_header, "Cedros")
    endpoint = f"{BUILDINGS}/{building}/services"
    data = {"name": "Agua", "calculation_type": "METERED"}
    assert client.post("/api/auth/logout", headers=session_header).status_code == 204
    assert client.get(endpoint).status_code == 401
    assert client.post(endpoint, json=data, headers=session_header).status_code == 401
    assert sign_in("test-owner").status_code == 200
    assert client.get(endpoint).status_code == 403
    assert client.post(endpoint, json=data, headers=session_header).status_code == 403


def test_database_rejects_unsupported_repartition(admin, session_header, sessions):
    building_id = UUID(create_building(admin, session_header, "Cedros"))
    statement = text(
        "INSERT INTO service_categories (id, building_id, name, calculation_type) "
        "VALUES (:id, :building_id, :name, :calculation_type)"
    )
    with (
        pytest.raises(IntegrityError, match="ck_service_categories_calculation_type"),
        sessions.begin() as db,
    ):
        db.execute(
            statement,
            {
                "id": uuid4(),
                "building_id": building_id,
                "name": "Agua",
                "calculation_type": "OTHER",
            },
        )
