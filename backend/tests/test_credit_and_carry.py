from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.billing import invoices
from app.billing.models import ServiceInvoice, UnitCharge
from app.collections import ledger
from app.collections.models import BalanceCarryForward, Payment, PaymentApplication
from app.identity.models import Account, RoleName
from app.properties.service import lock_building


@pytest.fixture
def workspace(admin, session_header, sessions, test_password_hash):
    with sessions.begin() as db:
        db.add(
            Account(
                username="another-credit-owner",
                full_name="Otro propietario",
                role_name=RoleName.OWNER,
                password_hash=test_password_hash,
            )
        )

    def post(path, data):
        response = admin.post(path, json=data, headers=session_header)
        assert response.status_code == 201, response.text
        return response.json()

    owner = next(
        item["id"]
        for item in admin.get("/api/admin/owners").json()
        if item["username"] == "test-owner"
    )
    buildings, units, categories = [], [], []
    for name in ("Crédito local", "Otra propiedad"):
        building = post("/api/admin/buildings", {"name": name, "total_units": 1})
        path = f"/api/admin/buildings/{building['id']}"
        buildings.append(path)
        units.append(
            post(
                f"{path}/units",
                {
                    "number": "001",
                    "area_sqm": "50.00",
                    "owner": {"kind": "existing", "id": owner},
                },
            )["id"]
        )
        categories.append(
            post(f"{path}/services", {"name": "Cuota", "calculation_type": "LINEAR"})[
                "id"
            ]
        )

    def issue(year, month, amount="50.00", *, building=0, category=None):
        return post(
            f"{buildings[building]}/invoices",
            {
                "category_id": category or categories[building],
                "billing_year": year,
                "billing_month": month,
                "start_date": f"{year}-{month:02}-01",
                "end_date": f"{year}-{month:02}-25",
                "total_amount": amount,
            },
        )

    def pay(amount, *, building=0, request_id=None):
        return post(
            f"{buildings[building]}/units/{units[building]}/payments",
            {
                "request_id": request_id or str(uuid4()),
                "amount": amount,
                "received_on": "2026-12-20",
                "billing_year": 2026,
                "billing_month": 12,
            },
        )

    def statement(building=0):
        response = admin.get(f"{buildings[building]}/units/{units[building]}/statement")
        assert response.status_code == 200, response.text
        return response.json()

    return buildings, units, issue, pay, statement, post


def assert_reconciled(statement):
    for payment in statement["payments"]:
        assert sum(
            (Decimal(item["amount"]) for item in payment["applications"]), Decimal(0)
        ) + Decimal(payment["credit"]) == Decimal(payment["amount"])
        assert all(Decimal(item["amount"]) > 0 for item in payment["applications"])
    assert sum(
        Decimal(charge["balance"]) for charge in statement["charges"]
    ) == Decimal(statement["balance"])


def test_new_invoice_automatically_uses_credit_only_in_the_same_unit(
    admin, workspace, sign_in, sessions
):
    paths, units, issue, pay, statement, _ = workspace
    issue(2026, 12)
    paid = pay("70.00")
    assert paid["credit"] == "20.00"
    issue(2027, 1, building=1)
    assert statement(1)["balance"] == "50.00"
    january = issue(2027, 1)
    assert january["accounting_locked"] is True
    result = statement()
    assert (result["balance"], result["credit"]) == ("30.00", "0.00")
    assert result["payments"][0]["id"] == paid["id"]
    application = result["payments"][0]["applications"][-1]
    assert application["amount"] == "20.00" and application["automatic"] is True
    assert application["applied_by"] == "test-admin" and application["applied_at"]
    assert_reconciled(result)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1
        assert db.scalar(select(func.sum(PaymentApplication.amount_cents))) == 7000
    assert sign_in("test-owner").status_code == 200
    assert admin.get(f"/api/owner/properties/{units[0]}/statement").json() == result
    assert sign_in("another-credit-owner").status_code == 200
    assert admin.get(f"/api/owner/properties/{units[0]}/statement").status_code == 404
    assert admin.get(f"{paths[0]}/units/{units[0]}/statement").status_code == 403


def test_credit_waits_without_charges_and_consumes_oldest_payments_first(
    workspace, sessions
):
    _, _, issue, pay, statement, _ = workspace
    first = pay("20.00")
    with sessions.begin() as db:
        db.get(Payment, UUID(first["id"])).recorded_at = datetime.now(UTC) - timedelta(
            days=1
        )
    second = pay("40.00")
    assert statement()["credit"] == "60.00"
    issue(2026, 12)
    result = statement()
    by_id = {payment["id"]: payment for payment in result["payments"]}
    assert by_id[first["id"]]["credit"] == "0.00"
    assert by_id[second["id"]]["credit"] == "10.00"
    assert [a["amount"] for a in by_id[second["id"]]["applications"]] == ["30.00"]
    assert result["balance"] == "0.00"
    assert_reconciled(result)


def test_carry_keeps_source_snapshot_through_skipped_months_and_later_payments(
    admin, workspace, session_header, sessions
):
    paths, _units, issue, pay, statement, post = workspace
    original = issue(2026, 12)
    pay("10.00")
    issue(2027, 2)
    result = statement()
    carry = result["carry_forwards"][0]
    assert (
        carry["source_year"],
        carry["source_month"],
        carry["billing_year"],
        carry["billing_month"],
    ) == (2026, 12, 2027, 2)
    assert carry["amount"] == carry["balance"] == "40.00"
    assert carry["charge_id"] == result["charges"][0]["id"]
    assert carry["recorded_by"] == "test-admin"
    assert result["balance"] == "90.00"
    service = post(
        f"{paths[0]}/services", {"name": "Otra cuota", "calculation_type": "LINEAR"}
    )
    issue(2027, 2, "1.00", category=service["id"])
    assert statement()["carry_forwards"] == [carry]
    pay("45.00")
    after = statement()
    assert after["carry_forwards"][0] == {**carry, "balance": "0.00"}
    assert after["balance"] == "46.00"
    assert_reconciled(after)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(BalanceCarryForward)) == 1
        assert db.scalar(select(func.count()).select_from(UnitCharge)) == 3
    # The carried invoice remains protected after the original debt is paid.
    response = admin.put(
        f"{paths[0]}/invoices/{original['id']}",
        headers=session_header,
        json={
            "revision": original["revision"],
            "reason": "Cambio posterior al arrastre",
            "start_date": original["start_date"],
            "end_date": original["end_date"],
            "total_amount": "60.00",
        },
    )
    assert response.status_code == 409


def test_backdated_invoice_carries_to_existing_period_and_uses_remaining_credit(
    workspace,
):
    _, _, issue, pay, statement, _ = workspace
    issue(2027, 3, "10.00")
    pay("15.00")
    issue(2026, 12, "20.00")
    result = statement()
    assert (result["balance"], result["credit"]) == ("15.00", "0.00")
    assert result["carry_forwards"][0]["amount"] == "15.00"
    assert result["carry_forwards"][0]["billing_month"] == 3
    assert_reconciled(result)


@pytest.mark.parametrize("payment", ["10.00", "70.00"])
def test_failed_invoice_rolls_back_credit_and_carry_changes(
    admin, workspace, session_header, monkeypatch, sessions, payment
):
    paths, _, issue, pay, statement, _ = workspace
    original = issue(2026, 12)
    pay(payment)
    before = statement()
    real_settle = invoices.settle_building

    def fail(*args):
        real_settle(*args)
        raise RuntimeError("Fallo sintético tras aplicar el crédito")

    monkeypatch.setattr(invoices, "settle_building", fail)
    data = {
        key: original[key]
        for key in (
            "category_id",
            "start_date",
            "end_date",
            "total_amount",
            "billing_year",
            "billing_month",
        )
    }
    data.update(billing_year=2027, billing_month=1)
    with pytest.raises(RuntimeError, match="Fallo sintético"):
        admin.post(f"{paths[0]}/invoices", json=data, headers=session_header)
    assert statement() == before
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ServiceInvoice)) == 1
    monkeypatch.setattr(invoices, "settle_building", real_settle)
    issue(2027, 1)
    assert statement()["balance"] == ("30.00" if payment == "70.00" else "90.00")


def test_reconciliation_retries_preserve_applications_and_carries(workspace, sessions):
    paths, units, issue, pay, statement, _ = workspace
    issue(2026, 12)
    issue(2027, 1)
    pay("10.00")
    before = statement()
    with sessions.begin() as db:
        actor = db.scalar(select(Account.id).where(Account.username == "test-admin"))
        lock_building(db, UUID(paths[0].rsplit("/", 1)[-1]))
        ledger.settle_unit(db, UUID(units[0]), actor)
        ledger.settle_unit(db, UUID(units[0]), actor)
    assert statement() == before
