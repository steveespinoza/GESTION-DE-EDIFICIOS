from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.billing import adjustments
from app.billing.models import ChargeAdjustment, UnitCharge
from app.collections.models import (
    Payment,
    PaymentApplication,
    PaymentApplicationRelease,
)
from app.identity.models import Account, RoleName


@pytest.fixture
def workspace(admin, session_header, sessions, test_password_hash):
    with sessions.begin() as db:
        db.add(
            Account(
                username="adjustment-other-owner",
                full_name="Otra cuenta sintética",
                role_name=RoleName.OWNER,
                password_hash=test_password_hash,
            )
        )

    def post(path, data):
        response = admin.post(path, json=data, headers=session_header)
        assert response.status_code == 201, response.text
        return response.json()

    owners = {
        row["username"]: row["id"] for row in admin.get("/api/admin/owners").json()
    }
    paths, units, categories = [], [], []
    for index, username in enumerate(("test-owner", "adjustment-other-owner")):
        building = post(
            "/api/admin/buildings", {"name": f"Ajustes {index}", "total_units": 1}
        )
        path = f"/api/admin/buildings/{building['id']}"
        paths.append(path)
        unit = post(
            f"{path}/units",
            {
                "number": "001",
                "area_sqm": "50.00",
                "owner": {"kind": "existing", "id": owners[username]},
            },
        )
        units.append(unit["id"])
        categories.append(
            post(f"{path}/services", {"name": "Cuota", "calculation_type": "LINEAR"})[
                "id"
            ]
        )

    def issue(
        amount="100.00", *, month=12, year=2026, category=None, end_day=25, building=0
    ):
        return post(
            f"{paths[building]}/invoices",
            {
                "category_id": category or categories[building],
                "billing_year": year,
                "billing_month": month,
                "start_date": f"{year}-{month:02}-01",
                "end_date": f"{year}-{month:02}-{end_day:02}",
                "total_amount": amount,
            },
        )

    def pay(amount):
        return post(
            f"{paths[0]}/units/{units[0]}/payments",
            {
                "request_id": str(uuid4()),
                "billing_year": 2026,
                "billing_month": 12,
                "received_on": "2026-12-25",
                "amount": amount,
            },
        )

    def invoice_path(invoice):
        return f"{paths[0]}/invoices/{invoice['id']}"

    def adjust(
        invoice,
        amount,
        *,
        revision=None,
        request_id=None,
        reason="Corrección del cargo",
    ):
        detail = admin.get(invoice_path(invoice)).json()
        charge = detail["charges"][0]
        data = {
            "request_id": request_id or str(uuid4()),
            "revision": charge["adjustment_revision"] if revision is None else revision,
            "new_amount": amount,
            "reason": reason,
        }
        endpoint = f"{invoice_path(invoice)}/charges/{charge['id']}/adjustments"
        return admin.post(endpoint, json=data, headers=session_header), endpoint, data

    def statement():
        response = admin.get(f"{paths[0]}/units/{units[0]}/statement")
        assert response.status_code == 200, response.text
        return response.json()

    return SimpleNamespace(
        paths=paths,
        units=units,
        categories=categories,
        post=post,
        issue=issue,
        pay=pay,
        adjust=adjust,
        statement=statement,
        invoice_path=invoice_path,
    )


def assert_reconciled(statement):
    for payment in statement["payments"]:
        assert sum(
            (Decimal(item["net_amount"]) for item in payment["applications"]),
            Decimal(0),
        ) + Decimal(payment["credit"]) == Decimal(payment["amount"])
        assert all(Decimal(item["net_amount"]) >= 0 for item in payment["applications"])
    for charge in statement["charges"]:
        assert Decimal(charge["amount"]) == Decimal(
            charge["original_amount"]
        ) + Decimal(charge["adjustment"])
        assert (
            Decimal(charge["balance"])
            == Decimal(charge["amount"]) - Decimal(charge["applied"])
            >= 0
        )
    assert sum(Decimal(item["balance"]) for item in statement["charges"]) == Decimal(
        statement["balance"]
    )


@pytest.mark.parametrize(
    ("new_amount", "credit", "balance"),
    [
        ("80.00", "20.00", "0.00"),
        ("0.00", "100.00", "0.00"),
        ("120.00", "0.00", "20.00"),
    ],
)
def test_adjustment_preserves_original_charge_and_cash_payment(
    admin, workspace, sessions, new_amount, credit, balance
):
    original = workspace.issue()
    paid = workspace.pay("100.00")
    result, _, _ = workspace.adjust(original, new_amount)
    assert result.status_code == 201, result.text
    event = result.json()
    assert event["previous_amount"] == "100.00" and event["new_amount"] == new_amount
    assert event["recorded_by"] == "test-admin" and event["recorded_at"]
    statement = workspace.statement()
    assert (statement["balance"], statement["credit"]) == (balance, credit)
    assert statement["payments"][0]["id"] == paid["id"]
    assert statement["payments"][0]["amount"] == "100.00"
    detail = admin.get(workspace.invoice_path(original)).json()
    assert detail["total_amount"] == detail["charges"][0]["amount"] == "100.00"
    assert detail["charges"][0]["adjusted_amount"] == new_amount
    assert detail["adjusted_total_amount"] == new_amount
    assert detail["adjustments"] == statement["adjustments"] == [event]
    with sessions() as db:
        assert db.scalar(select(UnitCharge.amount_cents)) == 10000
        assert db.scalar(select(Payment.amount_cents)) == 10000
        assert db.scalar(select(PaymentApplication.amount_cents)) == 10000
    assert_reconciled(statement)


def test_repeated_reductions_and_increases_preserve_each_application(workspace):
    original = workspace.issue()
    workspace.pay("100.00")
    for amount, credit in (("80.00", "20.00"), ("95.00", "5.00"), ("70.00", "30.00")):
        result, _, _ = workspace.adjust(original, amount)
        assert result.status_code == 201, result.text
        statement = workspace.statement()
        assert statement["credit"] == credit and statement["balance"] == "0.00"
        assert_reconciled(statement)
    applications = statement["payments"][0]["applications"]
    assert [item["amount"] for item in applications] == ["100.00", "15.00"]
    assert [item["net_amount"] for item in applications] == ["70.00", "0.00"]
    assert [item["released_credit"] for item in statement["adjustments"]] == [
        "20.00",
        "0.00",
        "25.00",
    ]


def test_released_credit_automatically_covers_other_charges_in_the_unit(workspace):
    original = workspace.issue("50.00", end_day=10)
    other_service = workspace.post(
        f"{workspace.paths[0]}/services",
        {"name": "Segunda cuota", "calculation_type": "LINEAR"},
    )
    workspace.issue("50.00", category=other_service["id"])
    workspace.pay("70.00")
    result, _, _ = workspace.adjust(original, "30.00")
    assert result.status_code == 201, result.text
    statement = workspace.statement()
    assert (statement["balance"], statement["credit"]) == ("10.00", "0.00")
    assert [charge["applied"] for charge in statement["charges"]] == ["30.00", "40.00"]
    assert len(statement["payments"]) == 1
    assert len(statement["payments"][0]["applications"]) == 3
    assert_reconciled(statement)


def test_partial_payment_only_generates_credit_for_the_overpaid_portion(workspace):
    original = workspace.issue()
    workspace.pay("30.00")
    result, _, _ = workspace.adjust(original, "80.00")
    assert result.status_code == 201 and result.json()["released_credit"] == "0.00"
    assert workspace.statement()["balance"] == "50.00"
    result, _, _ = workspace.adjust(original, "20.00")
    assert result.status_code == 201 and result.json()["released_credit"] == "10.00"
    statement = workspace.statement()
    assert (statement["balance"], statement["credit"]) == ("0.00", "10.00")
    assert_reconciled(statement)


def test_carry_snapshot_remains_and_owner_sees_only_their_adjustments(
    admin, workspace, sign_in
):
    original = workspace.issue()
    workspace.issue("50.00", month=2, year=2027)
    before = workspace.statement()["carry_forwards"][0]
    result, endpoint, data = workspace.adjust(original, "80.00")
    assert result.status_code == 201, result.text
    statement = workspace.statement()
    assert statement["balance"] == "130.00"
    assert statement["carry_forwards"] == [{**before, "balance": "80.00"}]
    assert statement["payments"] == []
    assert sign_in("test-owner").status_code == 200
    own_path = f"/api/owner/properties/{workspace.units[0]}/statement"
    assert admin.get(own_path).json() == statement
    assert (
        admin.post(
            endpoint, json=data, headers={"X-Edificios-Request": "1"}
        ).status_code
        == 403
    )
    assert sign_in("adjustment-other-owner").status_code == 200
    assert admin.get(own_path).status_code == 404
    own = admin.get(f"/api/owner/properties/{workspace.units[1]}/statement").json()
    assert own["adjustments"] == []


def test_idempotency_stale_revision_validation_and_building_scope(
    admin, workspace, session_header, sessions
):
    original = workspace.issue()
    workspace.pay("100.00")
    result, endpoint, data = workspace.adjust(original, "80.00")
    assert result.status_code == 201
    repeated = admin.post(endpoint, json=data, headers=session_header)
    assert repeated.status_code == 200 and repeated.json() == result.json()
    assert (
        admin.post(
            endpoint, json={**data, "new_amount": "70.00"}, headers=session_header
        ).status_code
        == 409
    )
    assert (
        admin.post(
            endpoint,
            json={**data, "request_id": str(uuid4()), "new_amount": "70.00"},
            headers=session_header,
        ).status_code
        == 409
    )
    assert admin.post(endpoint, json=data).status_code == 403
    assert (
        admin.post(
            endpoint.replace(workspace.paths[0], workspace.paths[1]),
            json=data,
            headers=session_header,
        ).status_code
        == 404
    )
    for changes in (
        {"new_amount": "-0.01"},
        {"new_amount": "1.001"},
        {"new_amount": "NaN"},
        {"reason": "   "},
        {"recorded_by_id": str(uuid4())},
    ):
        invalid = admin.post(endpoint, json={**data, **changes}, headers=session_header)
        assert invalid.status_code == 422, invalid.text
    same, _, _ = workspace.adjust(original, "80.00")
    assert same.status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ChargeAdjustment)) == 1
        assert (
            db.scalar(select(func.count()).select_from(PaymentApplicationRelease)) == 1
        )


def test_open_invoice_uses_existing_correction_flow(workspace):
    original = workspace.issue()
    result, _, _ = workspace.adjust(original, "80.00")
    assert result.status_code == 409 and "está abierta" in result.json()["detail"]
    assert workspace.statement()["adjustments"] == []


def test_failure_rolls_back_adjustment_releases_and_credit(
    workspace, monkeypatch, sessions
):
    original = workspace.issue()
    workspace.pay("100.00")
    before = workspace.statement()
    real = adjustments.settle_unit

    def fail(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("Fallo sintético del ajuste")

    monkeypatch.setattr(adjustments, "settle_unit", fail)
    with pytest.raises(RuntimeError, match="Fallo sintético"):
        workspace.adjust(original, "80.00")
    assert workspace.statement() == before
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ChargeAdjustment)) == 0
        assert (
            db.scalar(select(func.count()).select_from(PaymentApplicationRelease)) == 0
        )


def test_metered_readings_and_original_split_remain_unchanged(admin, workspace):
    service = workspace.post(
        f"{workspace.paths[0]}/services",
        {"name": "Agua", "calculation_type": "METERED"},
    )
    original = workspace.post(
        f"{workspace.paths[0]}/invoices",
        {
            "category_id": service["id"],
            "billing_year": 2026,
            "billing_month": 12,
            "start_date": "2026-12-01",
            "end_date": "2026-12-25",
            "total_amount": "100.00",
            "total_volume": "2.000",
            "readings": [
                {
                    "unit_id": workspace.units[0],
                    "previous_reading": "1.000",
                    "current_reading": "2.123",
                }
            ],
        },
    )
    workspace.pay("100.00")
    result, _, _ = workspace.adjust(original, "80.00")
    assert result.status_code == 201, result.text
    detail = admin.get(workspace.invoice_path(original)).json()
    assert detail["charges"][0]["meter"] == original["charges"][0]["meter"]
    assert workspace.statement()["charges"][0]["consumption"] == "1.123"
