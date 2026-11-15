from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.billing.allocation import split_metered
from app.billing.models import MeterReading, ServiceInvoice, UnitCharge


@pytest.mark.parametrize(
    ("amount", "volume", "readings", "expected"),
    [
        (10000, 30000, [10000, 5000], [(3333, 2500), (1667, 2500)]),
        (10000, 3000, [1000, 1000, 1000], [(3334, 0), (3333, 0), (3333, 0)]),
        (1, 3000, [0, 0, 0], [(0, 1), (0, 0), (0, 0)]),
    ],
)
def test_metered_allocation_preserves_every_cent(amount, volume, readings, expected):
    assert split_metered(amount, volume, readings) == expected
    assert sum(own + common for own, common in expected) == amount


@pytest.fixture
def workspace(admin, session_header):
    def post(path, data):
        response = admin.post(path, json=data, headers=session_header)
        assert response.status_code == 201
        return response.json()

    first = post("/api/admin/buildings", {"name": "Cedros", "total_units": 2})
    other = post("/api/admin/buildings", {"name": "Flores", "total_units": 1})
    building = f"/api/admin/buildings/{first['id']}"
    other_building = f"/api/admin/buildings/{other['id']}"
    water = post(
        f"{building}/services", {"name": "Agua", "calculation_type": "METERED"}
    )
    gas = post(f"{building}/services", {"name": "Gas", "calculation_type": "METERED"})
    owner = admin.get("/api/admin/owners").json()[0]
    ids = [
        post(
            f"{building}/units",
            {
                "number": n,
                "area_sqm": "40",
                "owner": {"kind": "existing", "id": owner["id"]},
            },
        )["id"]
        for n in ("002", "001")
    ]
    return (
        f"{building}/invoices",
        f"{other_building}/invoices",
        water["id"],
        gas["id"],
        list(reversed(ids)),
    )


def payload(
    category,
    units,
    month=11,
    previous=("0", "0"),
    current=("10", "5"),
    volume="30",
    confirmed=False,
):
    return {
        "category_id": category,
        "billing_year": 2026,
        "billing_month": month,
        "start_date": f"2026-{month:02}-01",
        "end_date": f"2026-{month:02}-25",
        "total_amount": "100.00",
        "total_volume": volume,
        "readings": [
            {
                "unit_id": unit,
                "previous_reading": before,
                "current_reading": after,
                "rollover_confirmed": confirmed and index == 0,
            }
            for index, (unit, before, after) in enumerate(
                zip(units, previous, current, strict=True)
            )
        ],
    }


def defaults(client, endpoint, service, month):
    return client.get(
        f"{endpoint}/meter-readings",
        params={
            "category_id": service,
            "billing_year": 2026,
            "billing_month": month,
        },
    )


def test_metered_invoice_persists_split_and_scopes_previous_readings(
    admin, session_header, workspace, sign_in
):
    endpoint, other, water, gas, units = workspace
    assert [
        row["previous_reading"] for row in defaults(admin, endpoint, water, 11).json()
    ] == [None, None]
    created = admin.post(endpoint, json=payload(water, units), headers=session_header)
    assert created.status_code == 201
    invoice = created.json()
    assert invoice["total_volume"] == "30.000"
    assert invoice["common_volume"] == "15.000"
    assert [charge["amount"] for charge in invoice["charges"]] == ["58.33", "41.67"]
    assert [charge["meter"]["common_amount"] for charge in invoice["charges"]] == [
        "25.00",
        "25.00",
    ]
    assert [charge["meter"]["own_amount"] for charge in invoice["charges"]] == [
        "33.33",
        "16.67",
    ]
    assert admin.get(f"{endpoint}/{invoice['id']}").json() == invoice
    assert (
        admin.post(
            endpoint, json=payload(water, units), headers=session_header
        ).status_code
        == 409
    )
    assert [
        row["previous_reading"] for row in defaults(admin, endpoint, water, 12).json()
    ] == ["10.000", "5.000"]
    assert [
        row["previous_reading"] for row in defaults(admin, endpoint, gas, 12).json()
    ] == [None, None]
    assert [
        row["previous_reading"] for row in defaults(admin, endpoint, water, 11).json()
    ] == [None, None]
    assert defaults(admin, other, water, 12).status_code == 404

    stale = payload(water, units, month=12, previous=("9", "5"), current=("11", "6"))
    assert admin.post(endpoint, json=stale, headers=session_header).status_code == 409
    backfill = payload(water, units, month=10)
    assert (
        admin.post(endpoint, json=backfill, headers=session_header).status_code == 409
    )
    assert len(admin.get(endpoint).json()) == 1
    compatible = payload(water, units, month=10, current=("0", "0"))
    assert (
        admin.post(endpoint, json=compatible, headers=session_header).status_code == 201
    )
    assert admin.get(f"{endpoint}/{invoice['id']}").json() == invoice
    assert sign_in("test-owner").status_code == 200
    assert defaults(admin, endpoint, water, 12).status_code == 403


def test_counter_rollover_requires_confirmation_and_keeps_three_decimals(
    admin, session_header, workspace
):
    endpoint, _, water, _, units = workspace
    data = payload(
        water, units, previous=("99999.900", "0"), current=("0.100", "0"), volume="1"
    )
    assert admin.post(endpoint, json=data, headers=session_header).status_code == 409
    assert admin.get(endpoint).json() == []
    data["readings"][0]["rollover_confirmed"] = True
    saved = admin.post(endpoint, json=data, headers=session_header)
    assert saved.status_code == 201
    assert saved.json()["charges"][0]["meter"]["consumption"] == "0.200"
    assert saved.json()["charges"][0]["meter"]["rolled_over"] is True
    assert saved.json()["common_volume"] == "0.800"
    assert [charge["amount"] for charge in saved.json()["charges"]] == [
        "60.00",
        "40.00",
    ]


def test_excess_volume_and_incorrect_units_leave_no_partial_records(
    admin, session_header, workspace, sessions
):
    endpoint, _, water, _, units = workspace
    data = payload(water, units, current=("60", "60"), volume="100")
    exceeded = admin.post(endpoint, json=data, headers=session_header)
    assert exceeded.status_code == 409
    assert "supera el volumen" in exceeded.json()["detail"]

    data = payload(water, units)
    assert (
        admin.post(
            endpoint,
            json=data | {"readings": data["readings"][:1]},
            headers=session_header,
        ).status_code
        == 409
    )
    assert (
        admin.post(
            endpoint,
            json=data | {"readings": [data["readings"][0]] * 2},
            headers=session_header,
        ).status_code
        == 409
    )
    data["readings"][0]["unit_id"] = str(uuid4())
    assert admin.post(endpoint, json=data, headers=session_header).status_code == 409
    data["readings"][0]["current_reading"] = "10.0001"
    assert admin.post(endpoint, json=data, headers=session_header).status_code == 422

    with sessions() as db:
        for model in (ServiceInvoice, UnitCharge, MeterReading):
            assert db.scalar(select(func.count()).select_from(model)) == 0
