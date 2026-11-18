from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.collections import deadlines
from app.collections.models import CollectionDeadline
from app.identity.models import Account, RoleName


@pytest.fixture
def portfolio(admin, session_header, sessions, test_password_hash, monkeypatch):
    monkeypatch.setattr(deadlines, "business_today", lambda: date(2027, 1, 1))
    with sessions.begin() as db:
        db.add(
            Account(
                username="deadline-other",
                full_name="Otro propietario",
                role_name=RoleName.OWNER,
                password_hash=test_password_hash,
            )
        )

    def post(path, data):
        response = admin.post(path, json=data, headers=session_header)
        assert response.status_code == 201, response.text
        return response.json()

    owners = {
        item["username"]: item["id"] for item in admin.get("/api/admin/owners").json()
    }
    buildings = [
        post("/api/admin/buildings", {"name": name, "total_units": capacity})
        for name, capacity in (("Alameda", 2), ("Cedros", 1))
    ]
    paths = [f"/api/admin/buildings/{item['id']}" for item in buildings]
    units = [
        post(
            f"{paths[index]}/units",
            {
                "number": number,
                "area_sqm": "50",
                "owner": {"kind": "existing", "id": owners[owner]},
            },
        )["id"]
        for index, number, owner in (
            (0, "001", "test-owner"),
            (0, "002", "deadline-other"),
            (1, "003", "deadline-other"),
        )
    ]
    categories = [
        post(f"{paths[index]}/services", {"name": name, "calculation_type": "LINEAR"})[
            "id"
        ]
        for index, name in ((0, "Cuota"), (0, "Limpieza"), (1, "Cuota"))
    ]

    def issue(category, year, month, amount, building=0):
        return post(
            f"{paths[building]}/invoices",
            {
                "category_id": categories[category],
                "billing_year": year,
                "billing_month": month,
                "start_date": f"{year}-{month:02}-01",
                "end_date": f"{year}-{month:02}-25",
                "total_amount": amount,
            },
        )

    december = issue(0, 2026, 12, "100.02")
    issue(1, 2026, 12, "40.00")
    issue(0, 2027, 2, "60.00")
    issue(2, 2026, 12, "999.00", 1)

    def deadline(due="2026-12-31", revision=0, year=2026, month=12, request_id=None):
        data = {
            "request_id": request_id or str(uuid4()),
            "revision": revision,
            "billing_year": year,
            "billing_month": month,
            "due_date": due,
            "reason": "Fecha acordada",
        }
        return admin.post(
            f"{paths[0]}/collection-deadlines", json=data, headers=session_header
        ), data

    def pay(amount):
        return post(
            f"{paths[0]}/units/{units[0]}/payments",
            {
                "request_id": str(uuid4()),
                "billing_year": 2026,
                "billing_month": 12,
                "received_on": "2026-12-31",
                "amount": amount,
            },
        )

    return SimpleNamespace(
        paths=paths,
        units=units,
        buildings=buildings,
        december=december,
        deadline=deadline,
        pay=pay,
        post=post,
    )


def test_existing_periods_have_no_invented_due_date(admin, portfolio):
    board = admin.get(f"{portfolio.paths[0]}/collections").json()
    assert board["balance"] == "200.02"
    assert board["overdue_balance"] == "0.00"
    assert board["as_of"] == "2027-01-01"
    assert board["deadlines"] == []
    assert len(board["rows"]) == 4
    assert all(row["due_date"] is None for row in board["rows"])
    assert all(row["unit_id"] in portfolio.units[:2] for row in board["rows"])
    statement = admin.get(
        f"{portfolio.paths[0]}/units/{portfolio.units[0]}/statement"
    ).json()
    assert statement["balance"] == "100.01" and statement["overdue_balance"] == "0.00"
    assert all(c["due_date"] is None and not c["overdue"] for c in statement["charges"])


@pytest.mark.parametrize(
    ("due", "overdue"),
    [("2026-12-31", "70.01"), ("2027-01-01", "0.00"), ("2027-01-02", "0.00")],
)
def test_overdue_starts_the_day_after_deadline_for_all_services(
    admin, portfolio, due, overdue
):
    response, _ = portfolio.deadline(due)
    assert response.status_code == 201
    board = admin.get(f"{portfolio.paths[0]}/collections").json()
    row = next(
        row
        for row in board["rows"]
        if row["unit_id"] == portfolio.units[0] and row["billing_year"] == 2026
    )
    assert (row["balance"], row["overdue_balance"], row["due_date"]) == (
        "70.01",
        overdue,
        due,
    )
    statement = admin.get(
        f"{portfolio.paths[0]}/units/{portfolio.units[0]}/statement"
    ).json()
    assert statement["overdue_balance"] == overdue
    assert all(
        c["due_date"] == due for c in statement["charges"] if c["billing_year"] == 2026
    )
    assert all(
        not c["overdue"] and c["due_date"] is None
        for c in statement["charges"]
        if c["billing_year"] == 2027
    )


def test_deadline_changes_preserve_history_and_protect_retries(
    admin, portfolio, sessions, session_header
):
    first, data = portfolio.deadline()
    assert first.status_code == 201
    repeat = admin.post(
        f"{portfolio.paths[0]}/collection-deadlines", json=data, headers=session_header
    )
    assert repeat.status_code == 200 and repeat.json() == first.json()
    changed = admin.post(
        f"{portfolio.paths[0]}/collection-deadlines",
        json={**data, "due_date": "2027-01-10"},
        headers=session_header,
    )
    assert changed.status_code == 409
    stale, _ = portfolio.deadline("2027-01-10")
    assert stale.status_code == 409
    revised, _ = portfolio.deadline("2027-01-10", revision=1)
    assert revised.status_code == 201 and revised.json()["revision"] == 2
    board = admin.get(f"{portfolio.paths[0]}/collections").json()
    assert [item["due_date"] for item in board["deadlines"]] == [
        "2027-01-10",
        "2026-12-31",
    ]
    assert all(
        item["recorded_by"] == "test-admin" and item["recorded_at"]
        for item in board["deadlines"]
    )
    assert board["overdue_balance"] == "0.00"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CollectionDeadline)) == 2


def test_overdue_reconciles_payments_adjustments_and_origin_carries(
    admin, sign_in, portfolio
):
    assert portfolio.deadline()[0].status_code == 201
    assert portfolio.deadline("2027-02-28", year=2027, month=2)[0].status_code == 201
    portfolio.pay("10.00")
    charge = next(
        c for c in portfolio.december["charges"] if c["unit_id"] == portfolio.units[0]
    )
    portfolio.post(
        f"{portfolio.paths[0]}/invoices/{portfolio.december['id']}/charges/{charge['id']}/adjustments",
        {
            "request_id": str(uuid4()),
            "revision": 0,
            "new_amount": "5.01",
            "reason": "Corrección con liberación",
        },
    )
    board = admin.get(f"{portfolio.paths[0]}/collections").json()
    own = [row for row in board["rows"] if row["unit_id"] == portfolio.units[0]]
    assert sum(Decimal(row["balance"]) for row in own) == Decimal("45.01")
    assert (
        next(row for row in own if row["billing_year"] == 2026)["overdue_balance"]
        == "15.01"
    )
    assert sign_in("test-owner").status_code == 200
    statement = admin.get(
        f"/api/owner/properties/{portfolio.units[0]}/statement"
    ).json()
    assert (
        statement["balance"],
        statement["overdue_balance"],
        statement["credit"],
    ) == ("45.01", "15.01", "0.00")
    assert len(statement["carry_forwards"]) == 2
    assert all(
        c["overdue"] == (c["billing_year"] == 2026 and c["balance"] != "0.00")
        for c in statement["charges"]
    )
    assert (
        admin.get(f"/api/owner/properties/{portfolio.units[1]}/statement").status_code
        == 404
    )
    assert sign_in("test-admin").status_code == 200
    portfolio.pay("50.00")
    statement = admin.get(
        f"{portfolio.paths[0]}/units/{portfolio.units[0]}/statement"
    ).json()
    assert (
        statement["balance"],
        statement["overdue_balance"],
        statement["credit"],
    ) == ("0.00", "0.00", "4.99")
    assert not any(c["overdue"] for c in statement["charges"])


def test_roles_unknown_buildings_and_invalid_deadlines(
    client, sign_in, portfolio, session_header
):
    read = f"{portfolio.paths[0]}/collections"
    write = f"{portfolio.paths[0]}/collection-deadlines"
    _, valid = portfolio.deadline()
    assert sign_in("test-owner").status_code == 200
    assert client.get(read).status_code == 403
    assert client.post(write, json=valid, headers=session_header).status_code == 403
    assert sign_in("deadline-other").status_code == 200
    assert client.get(read).status_code == 403
    assert sign_in("test-admin").status_code == 200
    assert client.get(f"/api/admin/buildings/{uuid4()}/collections").status_code == 404
    assert (
        client.post(
            f"/api/admin/buildings/{uuid4()}/collection-deadlines",
            json=valid,
            headers=session_header,
        ).status_code
        == 404
    )
    assert client.post(write, json=valid).status_code == 403
    for invalid in (
        {"billing_month": 13},
        {"billing_year": 2019},
        {"due_date": "2027-02-30"},
        {"reason": " "},
        {"revision": -1},
        {"revision": True},
    ):
        assert (
            client.post(
                write, json={**valid, **invalid}, headers=session_header
            ).status_code
            == 422
        )
    client.cookies.clear()
    assert client.get(read).status_code == 401
    assert client.post(write, json=valid, headers=session_header).status_code == 401


def test_business_day_uses_lima_at_utc_midnight():
    with patch("app.collections.deadlines.datetime") as clock:
        clock.now.side_effect = lambda zone: datetime(
            2027, 1, 1, 2, tzinfo=UTC
        ).astimezone(zone)
        assert deadlines.business_today() == date(2026, 12, 31)
