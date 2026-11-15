from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing import invoices
from app.billing.invoice_schemas import LinearInvoiceInput
from app.billing.models import (
    CalculationType,
    ServiceCategory,
    ServiceInvoice,
    UnitCharge,
)
from app.identity.models import Account, RoleName
from app.properties.models import Building, Unit

BUILDINGS = "/api/admin/buildings"


def create_record(admin, path, data, headers):
    response = admin.post(path, json=data, headers=headers)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def invoice_workspace(admin, session_header):
    primary = create_record(
        admin, BUILDINGS, {"name": "Cedros", "total_units": 4}, session_header
    )
    other = create_record(
        admin, BUILDINGS, {"name": "Flores", "total_units": 2}, session_header
    )
    building_url = f"{BUILDINGS}/{primary['id']}"
    catalog = f"{building_url}/services"
    category = create_record(
        admin,
        catalog,
        {"name": "Mantenimiento", "calculation_type": "LINEAR"},
        session_header,
    )
    owner = admin.get("/api/admin/owners").json()[0]
    units = {}
    for number in ("003", "001", "002"):
        units[number] = create_record(
            admin,
            f"{building_url}/units",
            {
                "number": number,
                "area_sqm": "40.00",
                "owner": {"kind": "existing", "id": owner["id"]},
            },
            session_header,
        )
    create_record(
        admin,
        f"{BUILDINGS}/{other['id']}/units",
        {
            "number": "004",
            "area_sqm": "40.00",
            "owner": {"kind": "existing", "id": owner["id"]},
        },
        session_header,
    )
    return (
        building_url,
        f"{BUILDINGS}/{other['id']}",
        units,
        {
            "category_id": category["id"],
            "billing_year": 2026,
            "billing_month": 11,
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "total_amount": "100.00",
        },
    )


def test_invoice_persists_exact_charges_and_unit_number_snapshot(
    admin, session_header, sessions, invoice_workspace
):
    building, _, units, data = invoice_workspace
    endpoint = f"{building}/invoices"
    assert admin.get(endpoint).json() == []
    invoice = create_record(admin, endpoint, data, session_header)
    charges = [
        {"unit_id": units[number]["id"], "unit_number": number, "amount": amount}
        for number, amount in (("001", "33.34"), ("002", "33.33"), ("003", "33.33"))
    ]
    assert invoice["total_amount"] == "100.00"
    assert invoice["charges"] == charges
    assert sum(Decimal(charge["amount"]) for charge in invoice["charges"]) == Decimal(
        "100.00"
    )
    with sessions() as db:
        persisted = db.get(ServiceInvoice, UUID(invoice["id"]))
        assert persisted is not None and persisted.total_cents == 10000
        saved = db.scalars(
            select(UnitCharge).where(UnitCharge.invoice_id == persisted.id)
        ).all()
        assert sorted(charge.amount_cents for charge in saved) == [3333, 3333, 3334]

    unit = units["001"]["id"]
    assert (
        admin.put(
            f"{building}/units/{unit}",
            json={"number": "009", "area_sqm": "40.00"},
            headers=session_header,
        ).status_code
        == 200
    )
    assert admin.get(f"{endpoint}/{invoice['id']}").json() == invoice
    assert admin.get(endpoint).json() == [
        {key: value for key, value in invoice.items() if key != "charges"}
    ]


def test_duplicate_period_leaves_original_charges_unchanged(
    admin, session_header, invoice_workspace
):
    building, _, _, data = invoice_workspace
    endpoint = f"{building}/invoices"
    first = create_record(admin, endpoint, data, session_header)
    duplicated = admin.post(
        endpoint, json=data | {"total_amount": "200.00"}, headers=session_header
    )
    assert duplicated.status_code == 409
    assert admin.get(f"{endpoint}/{first['id']}").json() == first
    second = create_record(
        admin,
        endpoint,
        data
        | {"billing_month": 12, "start_date": "2026-12-01", "end_date": "2026-12-31"},
        session_header,
    )
    assert [invoice["id"] for invoice in admin.get(endpoint).json()] == [
        second["id"],
        first["id"],
    ]


def test_invoice_access_is_scoped_to_its_building(
    admin, sign_in, session_header, invoice_workspace
):
    building, other, _, data = invoice_workspace
    invoice = create_record(admin, f"{building}/invoices", data, session_header)
    assert admin.get(f"{other}/invoices/{invoice['id']}").status_code == 404
    assert (
        admin.post(f"{other}/invoices", json=data, headers=session_header).status_code
        == 404
    )
    assert admin.get(f"{other}/invoices").json() == []
    assert sign_in("test-owner").status_code == 200
    for path in (f"{building}/invoices", f"{building}/invoices/{invoice['id']}"):
        assert admin.get(path).status_code == 403
    assert (
        admin.post(
            f"{building}/invoices", json=data, headers=session_header
        ).status_code
        == 403
    )


def test_requires_linear_service_and_at_least_one_unit(
    admin, session_header, invoice_workspace
):
    building, _, _, data = invoice_workspace
    metered = create_record(
        admin,
        f"{building}/services",
        {"name": "Agua", "calculation_type": "METERED"},
        session_header,
    )
    response = admin.post(
        f"{building}/invoices",
        json=data | {"category_id": metered["id"]},
        headers=session_header,
    )
    assert response.status_code == 409
    assert admin.get(f"{building}/invoices").json() == []

    empty = create_record(
        admin, BUILDINGS, {"name": "Vacío", "total_units": 1}, session_header
    )
    empty_url = f"{BUILDINGS}/{empty['id']}"
    category = create_record(
        admin,
        f"{empty_url}/services",
        {"name": "Limpieza", "calculation_type": "LINEAR"},
        session_header,
    )
    response = admin.post(
        f"{empty_url}/invoices",
        json=data | {"category_id": category["id"]},
        headers=session_header,
    )
    assert response.status_code == 409
    assert admin.get(f"{empty_url}/invoices").json() == []


@pytest.mark.parametrize(
    "change",
    [
        {"billing_month": 13},
        {"billing_year": 2019},
        {"end_date": "2026-10-31"},
        {"total_amount": "0.00"},
        {"total_amount": "20.001"},
    ],
)
def test_invalid_invoice_creates_no_records(
    admin, session_header, invoice_workspace, change
):
    building, _, _, data = invoice_workspace
    endpoint = f"{building}/invoices"
    assert (
        admin.post(endpoint, json=data | change, headers=session_header).status_code
        == 422
    )
    assert admin.get(endpoint).json() == []


def test_failure_to_persist_a_charge_rolls_back_invoice(
    admin, session_header, sessions, invoice_workspace, monkeypatch
):
    building, _, _, data = invoice_workspace
    monkeypatch.setattr(
        invoices, "split_linear", lambda _total, _count: [3334, -1, 6667]
    )
    with pytest.raises(IntegrityError, match="ck_unit_charges_amount"):
        admin.post(f"{building}/invoices", json=data, headers=session_header)
    assert admin.get(f"{building}/invoices").json() == []
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(UnitCharge)) == 0


def test_missing_invoices_and_writes_without_marker(admin, invoice_workspace):
    building, _, _, data = invoice_workspace
    endpoint = f"{building}/invoices"
    assert admin.get(f"{endpoint}/{uuid4()}").status_code == 404
    assert admin.get(f"{BUILDINGS}/{uuid4()}/invoices").status_code == 404
    assert admin.post(endpoint, json=data).status_code == 403
    assert admin.get(endpoint).json() == []


def test_concurrent_invoice_creation_persists_one_invoice_and_its_charges(
    engine, test_password_hash
):
    building_id, owner_id, category_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as db, db.begin():
        db.add(Building(id=building_id, name="Concurrencia", total_units=1))
        db.add(
            Account(
                id=owner_id,
                username=f"invoice-test-{owner_id}",
                full_name="Cuenta de concurrencia",
                password_hash=test_password_hash,
                role_name=RoleName.OWNER.value,
            )
        )
        db.flush()
        db.add(
            Unit(
                building_id=building_id,
                owner_id=owner_id,
                number="001",
                area_sqm=Decimal(30),
            )
        )
        db.add(
            ServiceCategory(
                id=category_id,
                building_id=building_id,
                name="General",
                calculation_type=CalculationType.LINEAR,
            )
        )
    data = LinearInvoiceInput.model_validate(
        {
            "category_id": category_id,
            "billing_year": 2026,
            "billing_month": 11,
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "total_amount": "100.00",
        }
    )
    barrier = Barrier(2)

    def save():
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            try:
                invoices.create_invoice(db, building_id, data)
            except invoices.InvoiceConflict:
                return False
            return True

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [executor.submit(save) for _ in range(2)]
            assert sorted(attempt.result(timeout=15) for attempt in attempts) == [
                False,
                True,
            ]
        with Session(engine) as db:
            invoice = db.scalars(
                select(ServiceInvoice).where(ServiceInvoice.category_id == category_id)
            ).one()
            charge = db.scalars(
                select(UnitCharge).where(UnitCharge.invoice_id == invoice.id)
            ).one()
            assert charge.amount_cents == invoice.total_cents == 10000
    finally:
        with Session(engine) as db, db.begin():
            ids = select(ServiceInvoice.id).where(
                ServiceInvoice.category_id == category_id
            )
            db.execute(delete(UnitCharge).where(UnitCharge.invoice_id.in_(ids)))
            db.execute(
                delete(ServiceInvoice).where(ServiceInvoice.category_id == category_id)
            )
            db.execute(delete(ServiceCategory).where(ServiceCategory.id == category_id))
            db.execute(delete(Unit).where(Unit.building_id == building_id))
            db.execute(delete(Building).where(Building.id == building_id))
            db.execute(delete(Account).where(Account.id == owner_id))
