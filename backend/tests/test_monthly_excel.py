from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_charge_adjustments import workspace as adjustment_workspace
from test_collections import ledger as metered_ledger
from test_consolidation import pdf_text
from test_credit_concurrency import committed_portfolio as committed_data
from test_credit_concurrency import invoice_input
from test_deadlines import portfolio as deadline_portfolio
from test_transparency import NS, Spreadsheet

from app.billing.invoices import create_invoice
from app.collections.schemas import PaymentInput
from app.collections.service import record_payment
from app.documents.monthly import read_monthly
from app.documents.monthly_excel import render_monthly
from app.properties.models import Building

portfolio = deadline_portfolio
workspace = adjustment_workspace
ledger = metered_ledger
committed_portfolio = committed_data


def download(client, path, year=2026, month=12):
    return client.get(
        f"{path}/monthly.xlsx", params={"billing_year": year, "billing_month": month}
    )


def book(response):
    return Spreadsheet(response, filename_prefix="mensual")


def test_monthly_reconciles_units_services_statements_and_pdf(admin, portfolio):
    portfolio.deadline()
    portfolio.pay("10.00")
    export = book(download(admin, portfolio.paths[0]))
    assert list(export.sheets) == ["Consolidado", "Matriz de servicios", "Detalle"]
    assert export.value("Consolidado", "A10") == "001"
    assert export.value("Consolidado", "B5") > 45000  # Typed first day of month.
    # Two services; columns E:K hold financial amounts, followed by coverage.
    assert [export.value("Consolidado", f"{col}12") for col in "EFGHIJK"] == [
        Decimal("140.02"),
        10,
        Decimal("130.02"),
        0,
        Decimal("130.02"),
        Decimal("130.02"),
        0,
    ]
    for row, unit in enumerate(portfolio.units[:2], 10):
        statement = admin.get(f"{portfolio.paths[0]}/units/{unit}/statement").json()
        current = [c for c in statement["charges"] if c["billing_year"] == 2026]
        assert export.value("Consolidado", f"E{row}") == sum(
            Decimal(c["amount"]) for c in current
        )
        assert export.value("Consolidado", f"I{row}") == sum(
            Decimal(c["balance"]) for c in current
        )
    assert export.value("Matriz de servicios", "N9") == Decimal("140.02")
    assert export.value("Matriz de servicios", "O9") == 10
    assert export.value("Matriz de servicios", "Q9") == 0
    assert export.value("Matriz de servicios", "F7") == 2
    assert export.value("Matriz de servicios", "K7") == Decimal("50.01")
    assert export.value("Matriz de servicios", "G7") is None  # Linear has no volume.
    assert export.formula("Consolidado", "I10") == "ROUND(SUM(G10:H10),2)"
    assert export.formula("Detalle", "L7") == "ROUND(SUM(J7:K7),2)"
    assert export.sheets["Detalle"].find("s:autoFilter", NS).attrib["ref"] == "A6:P10"
    assert (
        export.sheets["Matriz de servicios"].find("s:autoFilter", NS).attrib["ref"]
        == "A6:R8"
    )
    assert (
        export.sheets["Consolidado"].find("s:autoFilter", NS).attrib["ref"] == "A9:M11"
    )
    assert "130,02" in pdf_text(
        admin.get(
            f"{portfolio.paths[0]}/consolidation.pdf",
            params={"billing_year": 2026, "billing_month": 12},
        )
    )
    assert not any(
        "externalLink" in name or "vbaProject" in name for name in export.zip.namelist()
    )


def test_monthly_previous_balance_excludes_future_and_keeps_credit_separate(
    admin, portfolio
):
    portfolio.pay("10.00")
    export = book(download(admin, portfolio.paths[0], 2027, 2))
    # One service, previous December debt is counted once.
    assert [export.value("Consolidado", f"{col}12") for col in "DEFGHIJ"] == [
        60,
        0,
        60,
        Decimal("130.02"),
        Decimal("190.02"),
        0,
        0,
    ]
    earlier = book(download(admin, portfolio.paths[0]))
    assert earlier.value("Consolidado", "I12") == Decimal("130.02")
    assert "30" not in [
        str(earlier.value("Detalle", f"J{row}")) for row in range(7, 11)
    ]


def test_monthly_adjustments_release_applications_and_preserve_source(admin, workspace):
    invoice = workspace.issue()
    workspace.pay("110.00")
    assert workspace.adjust(invoice, "90.00")[0].status_code == 201
    export = book(download(admin, workspace.paths[0]))
    assert [export.value("Matriz de servicios", f"{col}7") for col in "EMNOPQ"] == [
        100,
        -10,
        90,
        90,
        0,
        0,
    ]
    assert [export.value("Detalle", f"{col}7") for col in "JKLMN"] == [
        100,
        -10,
        90,
        90,
        0,
    ]
    assert export.value("Consolidado", "J10") == 20
    assert export.value("Consolidado", "H10") == 0
    workspace.issue("50.00", year=2027, month=1)
    assert book(download(admin, workspace.paths[0])).value("Consolidado", "J10") == 0
    later = book(download(admin, workspace.paths[0], 2027, 1))
    assert later.value("Consolidado", "E10") == 20
    assert later.value("Consolidado", "H10") == 30


def test_monthly_metered_readings_common_and_original_divisor(
    admin, ledger, sessions, session_header
):
    paths, _units, _ = ledger
    building_id = paths[0].rsplit("/", 1)[-1]
    with sessions.begin() as db:
        db.get(Building, building_id).total_units = 2
    owner = admin.get("/api/admin/owners").json()[0]["id"]
    added = admin.post(
        f"{paths[0]}/units",
        json={
            "number": "002",
            "area_sqm": "40",
            "owner": {"kind": "existing", "id": owner},
        },
        headers=session_header,
    )
    assert added.status_code == 201
    export = book(download(admin, paths[0], 2027, 1))
    assert [export.value("Matriz de servicios", f"{col}7") for col in "FGHIJL"] == [
        1,
        1,
        1,
        0,
        50,
        0,
    ]
    assert [export.value("Detalle", f"{col}7") for col in "DEFGHI"] == [
        1,
        2,
        1,
        50,
        0,
        None,
    ]
    assert export.value("Consolidado", "K11") == "Sin cargos del periodo"
    assert export.value("Consolidado", "C11") is None
    assert export.value("Consolidado", "D11") == 0
    assert export.value("Consolidado", "H12") == 100  # December and January.


def test_monthly_keeps_text_literal_and_keys_distinct(admin, portfolio, sessions):
    with sessions() as db:
        report = read_monthly(db, portfolio.buildings[0]["id"], 2026, 12)
    report.summary.building_name = '=HYPERLINK("https://example.com","texto")'
    report.summary.units[0].unit_number = "001"
    report.summary.units[1].unit_number = "1"
    report.summary.units[0].owner_name = "=1+1"
    report.summary.services[0].service = "*?~ ÁÉÍÓÚ & servicio"
    response = download(admin, portfolio.paths[0])
    response._content = render_monthly(report)
    export = book(response)
    assert export.value("Consolidado", "A2").startswith("=HYPERLINK")
    assert export.formula("Consolidado", "A2") is None
    assert export.value("Consolidado", "B10") == "=1+1"
    assert export.formula("Consolidado", "B10") is None
    assert export.value("Consolidado", "A10") == "001"
    assert export.value("Consolidado", "A11") == "1"
    assert export.value("Consolidado", "M10") != export.value("Consolidado", "M11")
    assert (
        export.sheets["Detalle"].find("s:cols/s:col[@min='15']", NS).attrib["hidden"]
        == "1"
    )


def test_monthly_remainder_common_volume_three_decimals_and_meter_rollover(
    admin, portfolio, sessions
):
    with sessions.begin() as db:
        db.get(Building, portfolio.buildings[0]["id"]).total_units = 3
    owner = admin.get("/api/admin/owners").json()[0]["id"]
    extra = portfolio.post(
        f"{portfolio.paths[0]}/units",
        {"number": "003", "area_sqm": "40", "owner": {"kind": "existing", "id": owner}},
    )
    linear = portfolio.post(
        f"{portfolio.paths[0]}/services",
        {"name": "Cuota noviembre", "calculation_type": "LINEAR"},
    )
    common = {
        "billing_year": 2026,
        "billing_month": 11,
        "start_date": "2026-11-01",
        "end_date": "2026-11-25",
        "total_amount": "100.00",
    }
    portfolio.post(
        f"{portfolio.paths[0]}/invoices", {**common, "category_id": linear["id"]}
    )
    metered = portfolio.post(
        f"{portfolio.paths[0]}/services",
        {"name": "Agua noviembre", "calculation_type": "METERED"},
    )
    portfolio.post(
        f"{portfolio.paths[0]}/invoices",
        {
            **common,
            "category_id": metered["id"],
            "total_volume": "5.000",
            "readings": [
                {
                    "unit_id": portfolio.units[0],
                    "previous_reading": "99999.500",
                    "current_reading": "0.611",
                    "rollover_confirmed": True,
                },
                {
                    "unit_id": portfolio.units[1],
                    "previous_reading": "10.000",
                    "current_reading": "10.889",
                },
                {
                    "unit_id": extra["id"],
                    "previous_reading": "0.000",
                    "current_reading": "0.000",
                },
            ],
        },
    )
    export = book(download(admin, portfolio.paths[0], 2026, 11))
    assert [export.value("Matriz de servicios", f"{col}7") for col in "FGHIJL"] == [
        3,
        5,
        2,
        3,
        20,
        20,
    ]
    assert [export.value("Detalle", f"{col}7") for col in "DEFGH"] == [
        Decimal("99999.500"),
        Decimal("0.611"),
        Decimal("1.111"),
        Decimal("22.22"),
        20,
    ]
    assert [export.value("Consolidado", f"D{row}") for row in (10, 11, 12)] == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]
    assert export.value("Consolidado", "E13") == 200
    assert export.value("Consolidado", "I13") == 200
    assert export.value("Matriz de servicios", "Q9") == 0


def test_monthly_role_building_and_period_scopes(
    admin, portfolio, sign_in, session_header
):
    assert book(download(admin, portfolio.paths[1])).value("Consolidado", "D11") == 999
    own = book(download(admin, portfolio.paths[0]))
    assert "Cedros" not in own.strings
    assert download(admin, f"/api/admin/buildings/{uuid4()}").status_code == 404
    assert download(admin, portfolio.paths[0], 2026, 11).status_code == 409
    for owner in ("test-owner", "deadline-other"):
        assert sign_in(owner).status_code == 200
        assert download(admin, portfolio.paths[0]).status_code == 403
        assert download(admin, portfolio.paths[1]).status_code == 403
    assert admin.post("/api/auth/logout", headers=session_header).status_code == 204
    assert download(admin, portfolio.paths[0]).status_code == 401


@pytest.mark.parametrize(
    "query",
    [
        "",
        "billing_year=2026",
        "billing_year=2019&billing_month=12",
        "billing_year=10000&billing_month=12",
        "billing_year=2026&billing_month=0",
        "billing_year=2026&billing_month=13",
    ],
)
def test_monthly_validates_period(admin, portfolio, query):
    assert admin.get(f"{portfolio.paths[0]}/monthly.xlsx?{query}").status_code == 422


def test_monthly_consistent_read_holds_lock_and_has_constant_query_count(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        create_invoice(db, building, invoice_input(categories[0]), actor)
    queries = []

    def count(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    with Session(engine) as reader, Session(engine) as writer:
        event.listen(engine, "before_cursor_execute", count)
        try:
            report = read_monthly(reader, building, 2027, 1)
            render_monthly(report)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert len(queries) == 5
        writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
        payment = PaymentInput(
            request_id=uuid4(),
            billing_year=2027,
            billing_month=1,
            amount="10.00",
            received_on="2027-01-07",
        )
        with pytest.raises(OperationalError) as error:
            record_payment(writer, building, unit, actor, payment)
        assert error.value.orig.sqlstate == "55P03"
        writer.rollback()
        assert report.summary.totals.total_pending == 50
        reader.rollback()
        record_payment(writer, building, unit, actor, payment)
    with Session(engine) as db:
        assert read_monthly(db, building, 2027, 1).summary.totals.total_pending == 40
