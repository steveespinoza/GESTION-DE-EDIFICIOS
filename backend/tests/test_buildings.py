from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.properties.models import Building

BUILDINGS = "/api/admin/buildings"
BUILDING = {
    "name": "Condominio Los Cedros",
    "address": "Av. de la Demo 148",
    "total_units": 12,
    "bank_name": "Banco de prueba",
    "account_number": "000017580",
    "cci": "00200000000000000017",
    "account_holder": "Junta Los Cedros",
    "contact_email": "pagos@example.com",
}


def test_admin_lists_creates_reads_and_updates_a_building(
    admin, session_header, sessions
):
    assert admin.get(BUILDINGS).json() == []

    created = admin.post(BUILDINGS, json=BUILDING, headers=session_header)
    assert created.status_code == 201
    building_id = created.json()["id"]
    detail_url = f"{BUILDINGS}/{building_id}"
    assert admin.get(detail_url).json() == {"id": building_id, **BUILDING}

    updated = {
        **BUILDING,
        "name": "Los Cedros Norte",
        "total_units": 15,
        "bank_name": "Banco de prueba II",
        "account_number": "   ",
    }
    saved = admin.put(detail_url, json=updated, headers=session_header)
    assert saved.status_code == 200
    assert admin.get(detail_url).json() == {
        "id": building_id,
        **updated,
        "account_number": None,
    }
    assert admin.get(BUILDINGS).json() == [
        {
            "id": building_id,
            "name": "Los Cedros Norte",
            "address": BUILDING["address"],
            "total_units": 15,
        }
    ]
    with sessions() as db:
        persisted = db.get(Building, UUID(building_id))
        assert persisted is not None
        assert persisted.cci == BUILDING["cci"]
        assert persisted.account_number is None
        assert persisted.total_units == 15


def test_list_order_is_case_insensitive_and_names_can_repeat(admin, session_header):
    names = ["zeta", "Altos", "Alameda", "alameda", "Alameda"]
    ids = []
    for name in names:
        response = admin.post(
            BUILDINGS, json={"name": name, "total_units": 0}, headers=session_header
        )
        assert response.status_code == 201
        ids.append(response.json()["id"])

    buildings = admin.get(BUILDINGS).json()
    assert [building["name"].lower() for building in buildings] == [
        "alameda",
        "alameda",
        "alameda",
        "altos",
        "zeta",
    ]
    assert {building["id"] for building in buildings} == set(ids)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "  "},
        {"total_units": -1},
        {"total_units": 2.5},
        {"total_units": 2_147_483_648},
        {"contact_email": "correo-invalido"},
    ],
)
def test_invalid_building_leaves_the_list_unchanged(admin, session_header, changes):
    response = admin.post(BUILDINGS, json=BUILDING | changes, headers=session_header)
    assert response.status_code == 422
    assert admin.get(BUILDINGS).json() == []


def test_missing_building_returns_not_found(admin, session_header):
    path = f"{BUILDINGS}/{uuid4()}"
    assert admin.get(path).status_code == 404
    assert admin.put(path, json=BUILDING, headers=session_header).status_code == 404


def test_buildings_require_a_superadmin_session(client, sign_in, session_header):
    path = f"{BUILDINGS}/{uuid4()}"
    for expected_status in (401, 403):
        assert client.get(BUILDINGS).status_code == expected_status
        assert client.get(path).status_code == expected_status
        assert (
            client.post(BUILDINGS, json=BUILDING, headers=session_header).status_code
            == expected_status
        )
        assert (
            client.put(path, json=BUILDING, headers=session_header).status_code
            == expected_status
        )
        if expected_status == 401:
            assert sign_in("test-owner").status_code == 200


def test_writes_require_the_session_header(admin, session_header):
    created = admin.post(BUILDINGS, json=BUILDING, headers=session_header)
    building_id = created.json()["id"]
    path = f"{BUILDINGS}/{building_id}"

    assert admin.post(BUILDINGS, json=BUILDING).status_code == 403
    assert admin.put(path, json=BUILDING | {"total_units": 1}).status_code == 403
    assert admin.get(path).json()["total_units"] == BUILDING["total_units"]


def test_database_rejects_negative_capacity(sessions):
    with (
        pytest.raises(IntegrityError, match="ck_buildings_total_units_nonnegative"),
        sessions.begin() as db,
    ):
        db.add(Building(name="Edificio de prueba", total_units=-1))
