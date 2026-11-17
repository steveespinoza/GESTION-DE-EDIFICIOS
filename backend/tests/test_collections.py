from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.collections.models import Payment, PaymentApplication
from app.identity.models import Account, RoleName


@pytest.fixture
def ledger(admin, session_header, sessions, test_password_hash):
    def create(path, data):
        response = admin.post(path, json=data, headers=session_header)
        assert response.status_code == 201, response.text
        return response.json()

    with sessions.begin() as db:
        db.add(
            Account(
                username="second-owner",
                full_name="Segunda cuenta de prueba",
                role_name=RoleName.OWNER.value,
                password_hash=test_password_hash,
            )
        )
    owners = {
        owner["username"]: owner["id"]
        for owner in admin.get("/api/admin/owners").json()
    }
    building, other = [
        create("/api/admin/buildings", {"name": name, "total_units": 1})
        for name in ("Cedros", "Flores")
    ]
    paths = [f"/api/admin/buildings/{item['id']}" for item in (building, other)]
    unit, other_unit = [
        create(
            f"{path}/units",
            {
                "number": "001",
                "area_sqm": "40.00",
                "owner": {"kind": "existing", "id": owners[name]},
            },
        )
        for path, name in zip(paths, ("test-owner", "second-owner"), strict=True)
    ]
    service = create(
        f"{paths[0]}/services", {"name": "Agua", "calculation_type": "METERED"}
    )
    invoices = []
    for year, month, previous, current in ((2026, 12, "0", "1"), (2027, 1, "1", "2")):
        invoices.append(
            create(
                f"{paths[0]}/invoices",
                {
                    "category_id": service["id"],
                    "billing_year": year,
                    "billing_month": month,
                    "start_date": f"{year}-{month:02}-01",
                    "end_date": f"{year}-{month:02}-25",
                    "total_amount": "50.00",
                    "total_volume": "1.000",
                    "readings": [
                        {
                            "unit_id": unit["id"],
                            "previous_reading": previous,
                            "current_reading": current,
                        }
                    ],
                },
            )
        )
    return paths, (unit["id"], other_unit["id"]), invoices


def payment_data(amount="10.00", **overrides):
    return {
        "request_id": str(uuid4()),
        "amount": amount,
        "received_on": "2027-01-07",
        "billing_year": 2027,
        "billing_month": 1,
        **overrides,
    }


def test_partial_payment_locks_original_invoice_and_replays_only_once(
    admin, session_header, ledger, sessions
):
    paths, (unit_id, _), invoices = ledger
    endpoint = f"{paths[0]}/units/{unit_id}"
    data = payment_data(reference="  AB-200  ")
    first = admin.post(f"{endpoint}/payments", json=data, headers=session_header)
    assert first.status_code == 201, first.text
    payment = first.json()
    assert payment["reference"] == "AB-200"
    assert payment["credit"] == "0.00"
    assert [(a["billing_month"], a["amount"]) for a in payment["applications"]] == [
        (12, "10.00")
    ]
    repeated = admin.post(f"{endpoint}/payments", json=data, headers=session_header)
    assert repeated.status_code == 200
    assert repeated.json() == payment
    changed = admin.post(
        f"{endpoint}/payments", json={**data, "amount": "20.00"}, headers=session_header
    )
    assert changed.status_code == 409

    statement = admin.get(f"{endpoint}/statement").json()
    assert statement["balance"] == "90.00"
    assert [
        (charge["balance"], charge["consumption"]) for charge in statement["charges"]
    ] == [
        ("40.00", "1.000"),
        ("50.00", "1.000"),
    ]
    assert statement["payments"] == [payment]
    paid_invoice, unpaid_invoice = [
        f"{paths[0]}/invoices/{invoice['id']}" for invoice in invoices
    ]
    assert admin.get(paid_invoice).json()["accounting_locked"] is True
    assert admin.get(unpaid_invoice).json()["accounting_locked"] is False
    correction = admin.put(
        paid_invoice,
        headers=session_header,
        json={
            "revision": 0,
            "start_date": "2026-12-01",
            "end_date": "2026-12-25",
            "total_amount": "51.00",
            "total_volume": "1.000",
            "reason": "Revisión",
            "readings": [
                {"unit_id": unit_id, "previous_reading": "0", "current_reading": "1"}
            ],
        },
    )
    assert correction.status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1
        assert db.scalar(select(PaymentApplication.amount_cents)) == 1000


def test_cutoff_credit_and_exact_payment_are_reconciled(admin, session_header, ledger):
    (building, _), (unit_id, _), _ = ledger
    endpoint = f"{building}/units/{unit_id}"
    december = admin.post(
        f"{endpoint}/payments",
        headers=session_header,
        json=payment_data(
            "60.00",
            billing_year=2026,
            billing_month=12,
        ),
    )
    assert december.status_code == 201
    assert december.json()["credit"] == "10.00"
    assert [item["amount"] for item in december.json()["applications"]] == ["50.00"]
    exact = admin.post(
        f"{endpoint}/payments", headers=session_header, json=payment_data("50.00")
    )
    assert exact.status_code == 201
    assert exact.json()["credit"] == "0.00"
    assert [item["billing_month"] for item in exact.json()["applications"]] == [1]
    statement = admin.get(f"{endpoint}/statement").json()
    assert statement["balance"] == "0.00"
    assert statement["credit"] == "10.00"


def test_payment_and_statement_enforce_role_scope_and_input(
    admin, session_header, ledger, sign_in
):
    (building, other), (unit_id, other_unit), _ = ledger
    admin_path = f"{building}/units/{unit_id}"
    foreign_path = f"{other}/units/{unit_id}"
    owner_path = "/api/owner/properties"
    assert admin.get(f"{foreign_path}/statement").status_code == 404
    assert (
        admin.post(
            f"{foreign_path}/payments", json=payment_data(), headers=session_header
        ).status_code
        == 404
    )
    assert admin.post(f"{admin_path}/payments", json=payment_data()).status_code == 403
    assert (
        admin.post(
            f"{admin_path}/payments", json=payment_data("1.001"), headers=session_header
        ).status_code
        == 422
    )
    assert sign_in("test-owner").status_code == 200
    own = admin.get(f"{owner_path}/{unit_id}/statement")
    assert own.status_code == 200 and own.json()["balance"] == "100.00"
    assert admin.get(f"{owner_path}/{other_unit}/statement").status_code == 404
    assert (
        admin.post(
            f"{admin_path}/payments", json=payment_data(), headers=session_header
        ).status_code
        == 403
    )
    assert sign_in("second-owner").status_code == 200
    assert admin.get(f"{owner_path}/{unit_id}/statement").status_code == 404
    empty = admin.get(f"{owner_path}/{other_unit}/statement").json()
    assert empty["charges"] == empty["payments"] == []
    assert empty["balance"] == empty["credit"] == "0.00"
