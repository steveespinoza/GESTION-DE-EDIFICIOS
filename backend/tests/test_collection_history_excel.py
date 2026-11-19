from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_charge_adjustments import workspace as adjustment_workspace
from test_credit_concurrency import committed_portfolio as committed_data
from test_credit_concurrency import invoice_input
from test_deadlines import portfolio as deadline_portfolio
from test_transparency import NS, Spreadsheet

from app.billing.invoices import create_invoice
from app.collections.schemas import PaymentInput
from app.collections.service import record_payment
from app.documents.collection_history import read_collection_history
from app.documents.collection_history_excel import render_collection_history
from app.properties.models import Building

portfolio = deadline_portfolio
workspace = adjustment_workspace
committed_portfolio = committed_data


def download(client, path):
    return client.get(f"{path}/collections.xlsx")


def book(response):
    return Spreadsheet(response, filename_prefix="cobranzas")


def test_history_periods_are_disjoint_and_gaps_do_not_duplicate_carries(
    admin, portfolio
):
    portfolio.pay("10.00")
    result = book(download(admin, portfolio.paths[0]))
    assert list(result.sheets) == ["Resumen", "Periodo 2027-02", "Periodo 2026-12"]
    assert result.value("Resumen", "B6") == Decimal("190.02")
    assert result.value("Resumen", "E12") == Decimal("190.02")
    assert result.value("Periodo 2026-12", "E9") == Decimal("130.02")
    assert result.value("Periodo 2026-12", "F9") == 0
    assert result.value("Periodo 2027-02", "E9") == 60
    assert result.value("Periodo 2027-02", "F9") == Decimal("130.02")
    assert result.value("Periodo 2027-02", "G9") == Decimal("190.02")
    assert result.value("Resumen", "A10") > result.value("Resumen", "A11")
    assert result.value("Periodo 2026-12", "A7") == "001"
    assert result.formula("Periodo 2026-12", "E7") == "ROUND(C7-D7,2)"
    assert (
        result.formula("Periodo 2027-02", "F7")
        == "SUMIFS('Periodo 2026-12'!$G$7:$G$8,'Periodo 2026-12'!$L$7:$L$8,$L7)"
    )
    assert (
        result.sheets["Periodo 2027-02"].find("s:autoFilter", NS).attrib["ref"]
        == "A6:L8"
    )
    assert not any(
        "externalLink" in name or "vbaProject" in name for name in result.zip.namelist()
    )


def test_history_reconciles_each_collection_row_and_monthly_pending(admin, portfolio):
    portfolio.pay("10.00")
    result = book(download(admin, portfolio.paths[0]))
    overview = admin.get(f"{portfolio.paths[0]}/collections").json()
    assert result.value("Resumen", "B6") == Decimal(overview["balance"])
    for source in overview["rows"]:
        sheet = f"Periodo {source['billing_year']}-{source['billing_month']:02}"
        row = 7 if source["unit_number"] == "001" else 8
        for col, field in (
            ("C", "amount"),
            ("D", "applied"),
            ("E", "balance"),
            ("H", "overdue_balance"),
        ):
            assert result.value(sheet, f"{col}{row}") == Decimal(source[field])
    for year, month in ((2026, 12), (2027, 2)):
        monthly = Spreadsheet(
            admin.get(
                f"{portfolio.paths[0]}/monthly.xlsx",
                params={"billing_year": year, "billing_month": month},
            ),
            filename_prefix="mensual",
        )
        pending_col = "I" if year == 2026 else "H"
        assert result.value(f"Periodo {year}-{month:02}", "G9") == monthly.value(
            "Consolidado", f"{pending_col}12"
        )


def test_history_adjustments_and_released_applications_reconcile(admin, portfolio):
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
    result = book(download(admin, portfolio.paths[0]))
    assert [result.value("Periodo 2026-12", f"{col}7") for col in "CDE"] == [
        Decimal("25.01"),
        10,
        Decimal("15.01"),
    ]
    assert result.value("Periodo 2027-02", "G7") == Decimal("45.01")
    assert result.value("Resumen", "B6") == Decimal("145.02")


def test_history_current_credit_is_separate_and_later_use_updates_all_periods(
    admin, workspace
):
    invoice = workspace.issue()
    workspace.pay("110.00")
    assert workspace.adjust(invoice, "90.00")[0].status_code == 201
    result = book(download(admin, workspace.paths[0]))
    assert result.value("Resumen", "E6") == 20
    assert result.value("Resumen", "B6") == 0
    assert result.value("Periodo 2026-12", "C7") == 90
    assert result.value("Periodo 2026-12", "D7") == 90
    workspace.issue("50.00", year=2027, month=1)
    result = book(download(admin, workspace.paths[0]))
    assert result.value("Resumen", "E6") == 0
    assert result.value("Resumen", "B6") == 30
    assert result.value("Periodo 2026-12", "E7") == 0
    assert result.value("Periodo 2027-01", "D7") == 20
    assert result.value("Periodo 2027-01", "G7") == 30


def test_history_keeps_new_units_without_charges_and_credit_only(
    admin, portfolio, sessions
):
    with sessions.begin() as db:
        db.get(Building, portfolio.buildings[0]["id"]).total_units = 3
    owner = admin.get("/api/admin/owners").json()[0]["id"]
    unit = portfolio.post(
        f"{portfolio.paths[0]}/units",
        {"number": "000", "area_sqm": "40", "owner": {"kind": "existing", "id": owner}},
    )
    portfolio.post(
        f"{portfolio.paths[0]}/units/{unit['id']}/payments",
        {
            "request_id": str(uuid4()),
            "billing_year": 2026,
            "billing_month": 12,
            "received_on": "2026-12-20",
            "amount": "7.03",
        },
    )
    result = book(download(admin, portfolio.paths[0]))
    assert result.value("Resumen", "E6") == Decimal("7.03")
    assert result.value("Resumen", "B6") == Decimal("200.02")
    assert result.value("Periodo 2027-02", "A7") == "000"
    assert [result.value("Periodo 2027-02", f"{col}7") for col in "CDEFGH"] == [0] * 6
    assert result.value("Periodo 2027-02", "K7") == "Sin cargos del periodo"
    assert result.value("Periodo 2026-12", "G10") == Decimal("140.02")


def test_history_unit_with_only_earlier_charges_keeps_its_pending(
    admin, portfolio, sessions
):
    with sessions.begin() as db:
        db.get(Building, portfolio.buildings[0]["id"]).total_units = 3
    owner = admin.get("/api/admin/owners").json()[0]["id"]
    portfolio.post(
        f"{portfolio.paths[0]}/units",
        {"number": "003", "area_sqm": "40", "owner": {"kind": "existing", "id": owner}},
    )
    service = portfolio.post(
        f"{portfolio.paths[0]}/services",
        {"name": "Cuota anterior", "calculation_type": "LINEAR"},
    )
    portfolio.post(
        f"{portfolio.paths[0]}/invoices",
        {
            "category_id": service["id"],
            "billing_year": 2026,
            "billing_month": 11,
            "start_date": "2026-11-01",
            "end_date": "2026-11-25",
            "total_amount": "100.00",
        },
    )
    result = book(download(admin, portfolio.paths[0]))
    assert result.value("Periodo 2027-02", "C9") == 0
    assert result.value("Periodo 2027-02", "F9") == Decimal("33.33")
    assert result.value("Periodo 2027-02", "G9") == Decimal("33.33")
    assert result.value("Periodo 2027-02", "K9") == "Sin cargos del periodo"
    assert result.value("Resumen", "B6") == Decimal("300.02")


def test_history_zero_revised_cargo_remains_a_registered_period(admin, workspace):
    invoice = workspace.issue()
    workspace.pay("10.00")
    assert workspace.adjust(invoice, "0.00")[0].status_code == 201
    result = book(download(admin, workspace.paths[0]))
    assert list(result.sheets) == ["Resumen", "Periodo 2026-12"]
    assert result.value("Periodo 2026-12", "C7") == 0
    assert result.value("Periodo 2026-12", "J7") == "Pagado"
    assert result.value("Periodo 2026-12", "K7") == "Con cargos"
    assert result.value("Resumen", "E6") == 10


@pytest.mark.parametrize(
    ("due", "overdue"), [("2027-01-01", Decimal(0)), ("2026-12-31", Decimal("140.02"))]
)
def test_history_overdue_uses_current_lima_date_and_origin_period(
    admin, portfolio, due, overdue
):
    assert portfolio.deadline(due)[0].status_code == 201
    result = book(download(admin, portfolio.paths[0]))
    assert result.value("Resumen", "F12") == overdue
    assert result.value("Periodo 2026-12", "H9") == overdue
    assert result.value("Periodo 2027-02", "H9") == 0
    assert result.value("Periodo 2026-12", "I7") > 45000


def test_history_owner_building_and_session_scopes(
    admin, portfolio, sign_in, session_header
):
    result = book(download(admin, portfolio.paths[0]))
    assert "Cedros" not in result.strings
    assert book(download(admin, portfolio.paths[1])).value("Resumen", "B6") == 999
    assert download(admin, f"/api/admin/buildings/{uuid4()}").status_code == 404
    for owner in ("test-owner", "deadline-other"):
        assert sign_in(owner).status_code == 200
        assert download(admin, portfolio.paths[0]).status_code == 403
        assert download(admin, portfolio.paths[1]).status_code == 403
    assert admin.post("/api/auth/logout", headers=session_header).status_code == 204
    assert download(admin, portfolio.paths[0]).status_code == 401


def test_history_empty_building_returns_clear_conflict(admin, portfolio):
    building = portfolio.post(
        "/api/admin/buildings", {"name": "Sin periodos", "total_units": 1}
    )
    response = download(admin, f"/api/admin/buildings/{building['id']}")
    assert response.status_code == 409
    assert "no tiene periodos con cargos" in response.json()["detail"]


def test_history_text_is_literal_and_identifiers_keep_leading_zeros(
    admin, portfolio, sessions
):
    with sessions() as db:
        data = read_collection_history(db, portfolio.buildings[0]["id"])
    data.overview.building_name = '=HYPERLINK("https://example.com","literal")'
    units = [
        replace(data.units[0], number="001", owner="=1+1"),
        replace(data.units[1], number="1", owner="*?~ Otra cuenta"),
    ]
    response = download(admin, portfolio.paths[0])
    response._content = render_collection_history(replace(data, units=units))
    result = book(response)
    assert result.value("Resumen", "A2").startswith("=HYPERLINK")
    assert result.formula("Resumen", "A2") is None
    assert result.value("Periodo 2027-02", "A7") == "001"
    assert result.value("Periodo 2027-02", "A8") == "1"
    assert result.value("Periodo 2027-02", "B7") == "=1+1"
    assert result.formula("Periodo 2027-02", "B7") is None
    assert result.value("Periodo 2027-02", "L7") != result.value(
        "Periodo 2027-02", "L8"
    )


def test_history_read_holds_building_lock_and_queries_do_not_grow_per_period(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        create_invoice(db, building, invoice_input(categories[0]), actor)
        create_invoice(db, building, invoice_input(categories[0], month=3), actor)
    queries = []

    def count(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    with Session(engine) as reader, Session(engine) as writer:
        event.listen(engine, "before_cursor_execute", count)
        try:
            data = read_collection_history(reader, building)
            render_collection_history(data)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert len(queries) == 4
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
        assert data.overview.balance == 100
        reader.rollback()
        record_payment(writer, building, unit, actor, payment)
    with Session(engine) as db:
        assert read_collection_history(db, building).overview.balance == 90
