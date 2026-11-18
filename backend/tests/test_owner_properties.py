from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.identity.models import Account, RoleName
from app.properties.models import Building, Unit
from app.properties.owner_service import list_properties

PROPERTIES = "/api/owner/properties"


@pytest.fixture
def portfolio(sessions, test_password_hash):
    identifiers = {
        name: uuid4()
        for name in (
            "cedros",
            "alameda",
            "los_pinos",
            "unit_a",
            "unit_b",
            "unit_c",
            "foreign_shared",
            "foreign",
        )
    }
    with sessions.begin() as db:
        owner_id = db.scalar(select(Account.id).where(Account.username == "test-owner"))
        assert owner_id is not None
        other = Account(
            username="test-other-owner",
            full_name="Otro propietario de prueba",
            password_hash=test_password_hash,
            role_name=RoleName.OWNER.value,
        )
        db.add_all(
            [
                other,
                Building(id=identifiers["cedros"], name="Cedros", total_units=3),
                Building(
                    id=identifiers["alameda"],
                    name="Alameda",
                    address="Av. de la Demo 148",
                    total_units=3,
                    bank_name="Banco de prueba",
                    account_number="000017580",
                    cci="00200000000000000017",
                    account_holder="Junta Alameda",
                    contact_email="pagos@example.com",
                ),
                Building(id=identifiers["los_pinos"], name="Los Pinos", total_units=3),
            ]
        )
        db.flush()
        for key, building, number, assignee in (
            ("unit_a", "cedros", "004", owner_id),
            ("unit_b", "alameda", "101-A", owner_id),
            ("unit_c", "alameda", "101-B", owner_id),
            ("foreign_shared", "alameda", "201", other.id),
            ("foreign", "los_pinos", "001", other.id),
        ):
            db.add(
                Unit(
                    id=identifiers[key],
                    building_id=identifiers[building],
                    number=number,
                    area_sqm=Decimal("45.50"),
                    owner_id=assignee,
                )
            )
    return {key: str(value) for key, value in identifiers.items()}


def test_list_groups_only_the_current_owners_units(client, sign_in, portfolio):
    assert sign_in("test-owner").status_code == 200
    response = client.get(PROPERTIES)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == [
        {
            "id": portfolio["alameda"],
            "name": "Alameda",
            "address": "Av. de la Demo 148",
            "units": [
                {
                    "id": portfolio["unit_b"],
                    "number": "101-A",
                    "area_sqm": "45.50",
                    "balance": "0.00",
                    "credit": "0.00",
                },
                {
                    "id": portfolio["unit_c"],
                    "number": "101-B",
                    "area_sqm": "45.50",
                    "balance": "0.00",
                    "credit": "0.00",
                },
            ],
        },
        {
            "id": portfolio["cedros"],
            "name": "Cedros",
            "address": None,
            "units": [
                {
                    "id": portfolio["unit_a"],
                    "number": "004",
                    "area_sqm": "45.50",
                    "balance": "0.00",
                    "credit": "0.00",
                }
            ],
        },
    ]

    assert sign_in("test-other-owner").status_code == 200
    other_properties = client.get(PROPERTIES).json()
    assert [
        (group["id"], [unit["id"] for unit in group["units"]])
        for group in other_properties
    ] == [
        (portfolio["alameda"], [portfolio["foreign_shared"]]),
        (portfolio["los_pinos"], [portfolio["foreign"]]),
    ]


def test_detail_exposes_only_the_owners_unit_and_its_payment_information(
    client, sign_in, portfolio
):
    assert sign_in("test-owner").status_code == 200
    response = client.get(f"{PROPERTIES}/{portfolio['unit_b']}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "id": portfolio["unit_b"],
        "number": "101-A",
        "area_sqm": "45.50",
        "building": {
            "id": portfolio["alameda"],
            "name": "Alameda",
            "address": "Av. de la Demo 148",
        },
        "payment_instructions": {
            "bank_name": "Banco de prueba",
            "account_number": "000017580",
            "cci": "00200000000000000017",
            "account_holder": "Junta Alameda",
            "contact_email": "pagos@example.com",
        },
    }
    without_payment = client.get(f"{PROPERTIES}/{portfolio['unit_a']}")
    assert without_payment.status_code == 200
    assert all(
        value is None
        for value in without_payment.json()["payment_instructions"].values()
    )


def test_foreign_units_and_unknown_identifiers_have_the_same_response(
    client, sign_in, portfolio
):
    for username, denied_keys in (
        ("test-owner", ("foreign", "foreign_shared")),
        ("test-other-owner", ("unit_a", "unit_b")),
    ):
        assert sign_in(username).status_code == 200
        for unit_id in (portfolio[denied_keys[0]], portfolio[denied_keys[1]], uuid4()):
            response = client.get(f"{PROPERTIES}/{unit_id}")
            assert response.status_code == 404
            assert response.json() == {"detail": "Unidad no encontrada."}
            assert response.headers["cache-control"] == "no-store"


def test_owner_without_units_receives_an_empty_list(client, sign_in):
    assert sign_in("test-owner").status_code == 200
    response = client.get(PROPERTIES)
    assert response.status_code == 200
    assert response.json() == []


def test_portfolio_totals_use_one_query_for_multiple_units(sessions, portfolio):
    with sessions() as db:
        owner_id = db.scalar(select(Account.id).where(Account.username == "test-owner"))
        statements = []

        def count_statements(conn, cursor, statement, parameters, context, many):
            statements.append(statement)

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", count_statements)
        try:
            groups = list_properties(db, owner_id)
        finally:
            event.remove(connection, "before_cursor_execute", count_statements)
        assert sum(len(group.units) for group in groups) == 3
        assert len(statements) == 1


def test_summary_reconciles_adjustments_releases_payments_and_carries(
    admin, sign_in, session_header, portfolio
):
    path = f"/api/admin/buildings/{portfolio['alameda']}"

    def post(endpoint, data):
        response = admin.post(endpoint, json=data, headers=session_header)
        assert response.status_code == 201, response.text
        return response.json()

    category = post(f"{path}/services", {"name": "Cuota", "calculation_type": "LINEAR"})

    def issue(year, month, amount):
        return post(
            f"{path}/invoices",
            {
                "category_id": category["id"],
                "billing_year": year,
                "billing_month": month,
                "start_date": f"{year}-{month:02}-01",
                "end_date": f"{year}-{month:02}-25",
                "total_amount": amount,
            },
        )

    def pay(key, amount):
        return post(
            f"{path}/units/{portfolio[key]}/payments",
            {
                "request_id": str(uuid4()),
                "billing_year": 2026,
                "billing_month": 12,
                "received_on": "2026-12-25",
                "amount": amount,
            },
        )

    december = issue(2026, 12, "300.03")  # S/ 100.01 per unit.
    pay("unit_b", "120.01")
    issue(2027, 2, "150.00")  # Credit applies; January has no invoice.
    pay("unit_b", "15.00")
    pay("unit_b", "15.00")
    charge = next(c for c in december["charges"] if c["unit_id"] == portfolio["unit_b"])
    endpoint = f"{path}/invoices/{december['id']}/charges/{charge['id']}/adjustments"
    post(
        endpoint,
        {
            "request_id": str(uuid4()),
            "revision": 0,
            "new_amount": "80.01",
            "reason": "Revisión",
        },
    )
    # Consume part of the released credit into a new application of the same charge.
    post(
        endpoint,
        {
            "request_id": str(uuid4()),
            "revision": 1,
            "new_amount": "95.01",
            "reason": "Revisión final",
        },
    )
    pay("foreign_shared", "10.01")
    # A credit-only unit in a different building must also appear.
    post(
        f"/api/admin/buildings/{portfolio['cedros']}/units/{portfolio['unit_a']}/payments",
        {
            "request_id": str(uuid4()),
            "billing_year": 2026,
            "billing_month": 12,
            "received_on": "2026-12-25",
            "amount": "7.03",
        },
    )

    for username, expected in (
        (
            "test-owner",
            {
                "unit_a": ("0.00", "7.03"),
                "unit_b": ("0.00", "5.00"),
                "unit_c": ("150.01", "0.00"),
            },
        ),
        (
            "test-other-owner",
            {"foreign_shared": ("140.00", "0.00"), "foreign": ("0.00", "0.00")},
        ),
    ):
        assert sign_in(username).status_code == 200
        response = admin.get(PROPERTIES)
        assert response.status_code == 200
        summaries = {
            unit["id"]: unit for group in response.json() for unit in group["units"]
        }
        assert set(summaries) == {portfolio[key] for key in expected}
        for key, totals in expected.items():
            summary = summaries[portfolio[key]]
            statement = admin.get(f"{PROPERTIES}/{portfolio[key]}/statement").json()
            assert (summary["balance"], summary["credit"]) == totals
            assert totals == (statement["balance"], statement["credit"])
            if key == "unit_c":
                assert len(statement["carry_forwards"]) == 1
                assert statement["carry_forwards"][0]["amount"] == "100.01"


@pytest.mark.parametrize("path", (PROPERTIES, f"{PROPERTIES}/{uuid4()}"))
def test_portal_requires_an_owner_session(client, sign_in, path):
    assert client.get(path).status_code == 401
    assert sign_in("test-admin").status_code == 200
    assert client.get(path).status_code == 403
