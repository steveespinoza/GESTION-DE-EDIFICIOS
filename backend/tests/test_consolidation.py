from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_charge_adjustments import workspace as adjustment_workspace
from test_collections import ledger as metered_ledger
from test_credit_concurrency import committed_portfolio as committed_data
from test_credit_concurrency import invoice_input
from test_deadlines import portfolio as deadline_portfolio

from app.billing.invoices import create_invoice
from app.collections.schemas import PaymentInput
from app.collections.service import record_payment
from app.documents.consolidated_pdf import render_consolidation
from app.documents.consolidation import read_consolidation
from app.documents.models import Receipt
from app.properties.models import Building

portfolio = deadline_portfolio
workspace = adjustment_workspace
ledger = metered_ledger
committed_portfolio = committed_data


def download(client, path, year=2026, month=12):
    return client.get(
        f"{path}/consolidation.pdf",
        params={"billing_year": year, "billing_month": month},
    )


def pdf_text(response):
    assert response.status_code == 200, (
        response.text[:500] if response.status_code != 200 else ""
    )
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="consolidado-'
    )
    assert response.content.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(response.content))
    assert all(page.mediabox.width > page.mediabox.height for page in reader.pages)
    return "\n".join(page.extract_text() for page in reader.pages)


def test_consolidation_reconciles_each_statement_and_overdue_sources(
    admin, portfolio, sessions
):
    assert portfolio.deadline()[0].status_code == 201
    portfolio.pay("10.00")
    with sessions() as db:
        report = read_consolidation(db, portfolio.buildings[0]["id"], 2027, 2)
    assert len(report.units) == 2
    assert report.totals.current_amount == 60
    assert report.totals.current_applied == 0
    assert report.totals.previous_balance == Decimal("130.02")
    assert report.totals.overdue_balance == Decimal("130.02")
    assert report.totals.total_pending == Decimal("190.02")
    assert report.due_date is None
    for unit in report.units:
        statement = admin.get(
            f"{portfolio.paths[0]}/units/{unit.unit_id}/statement"
        ).json()
        current = [c for c in statement["charges"] if c["billing_year"] == 2027]
        earlier = [c for c in statement["charges"] if c["billing_year"] == 2026]
        assert unit.current_amount == sum(Decimal(c["amount"]) for c in current)
        assert unit.current_applied == sum(Decimal(c["applied"]) for c in current)
        assert unit.previous_balance == sum(Decimal(c["balance"]) for c in earlier)
        assert unit.total_pending == Decimal(statement["balance"])
        assert unit.credit == Decimal(statement["credit"])
    contents = pdf_text(download(admin, portfolio.paths[0], year=2027, month=2))
    for expected in (
        "CONSOLIDADO MENSUAL",
        "febrero de 2027",
        "190,02",
        "130,02",
        "Uso administrativo",
        "Página",
        "Sin vencimiento",
    ):
        assert expected in contents
    assert "999,00" not in contents and "Cedros" not in contents


def test_current_month_excludes_later_charges_and_reconciles_service_totals(
    admin, portfolio, sessions
):
    with sessions() as db:
        report = read_consolidation(db, portfolio.buildings[0]["id"], 2026, 12)
    assert len(report.services) == 2
    assert sum(s.provider_amount for s in report.services) == Decimal("140.02")
    assert sum(s.amount for s in report.services) == report.totals.current_amount
    assert sum(s.applied for s in report.services) == report.totals.current_applied
    assert report.totals.total_pending == Decimal("140.02")
    assert report.totals.previous_balance == 0
    contents = pdf_text(download(admin, portfolio.paths[0]))
    assert "140,02" in contents and "30,00" not in contents


def test_adjustments_released_applications_and_future_credit_use(
    admin, workspace, sessions
):
    invoice = workspace.issue()
    workspace.pay("110.00")
    assert workspace.adjust(invoice, "90.00")[0].status_code == 201
    building = workspace.paths[0].rsplit("/", 1)[-1]
    with sessions() as db:
        report = read_consolidation(db, building, 2026, 12)
    service = report.services[0]
    assert service.provider_amount == 100 and service.adjustment == -10
    assert service.amount == service.applied == 90 and service.balance == 0
    assert report.totals.credit == 20 and report.totals.total_pending == 0
    workspace.issue("50.00", year=2027, month=1)
    with sessions() as db:
        earlier = read_consolidation(db, building, 2026, 12)
        later = read_consolidation(db, building, 2027, 1)
    assert earlier.totals.current_applied == 90
    assert earlier.totals.total_pending == earlier.totals.credit == 0
    assert later.totals.current_applied == 20
    assert later.totals.total_pending == 30 and later.totals.previous_balance == 0
    contents = pdf_text(download(admin, workspace.paths[0]))
    assert "-10,00" in contents and "90,00" in contents


def test_new_unit_without_monthly_charges_preserves_its_current_credit(
    admin, portfolio, sessions
):
    with sessions.begin() as db:
        db.get(Building, portfolio.buildings[0]["id"]).total_units = 3
    owner = admin.get("/api/admin/owners").json()[0]["id"]
    unit = portfolio.post(
        f"{portfolio.paths[0]}/units",
        {
            "number": "NUEVA-004",
            "area_sqm": "50",
            "owner": {"kind": "existing", "id": owner},
        },
    )
    portfolio.post(
        f"{portfolio.paths[0]}/units/{unit['id']}/payments",
        {
            "request_id": str(uuid4()),
            "billing_year": 2027,
            "billing_month": 4,
            "received_on": "2027-04-01",
            "amount": "7.03",
        },
    )
    with sessions() as db:
        report = read_consolidation(db, portfolio.buildings[0]["id"], 2026, 12)
    assert len(report.units) == 3
    new_unit = next(u for u in report.units if str(u.unit_id) == unit["id"])
    assert not new_unit.has_current_charges
    assert new_unit.total_pending == 0 and new_unit.credit == Decimal("7.03")
    assert report.totals.total_pending == Decimal("140.02")
    assert report.totals.credit == Decimal("7.03")
    contents = pdf_text(download(admin, portfolio.paths[0]))
    assert (
        "NUEVA-004" in contents
        and "Sin cargos del mes" in contents
        and "7,03" in contents
    )


def test_metered_sources_and_read_only_download(admin, ledger, sessions):
    paths, _, _ = ledger
    with sessions() as db:
        before = db.scalar(select(func.count()).select_from(Receipt))
        report = read_consolidation(db, paths[0].rsplit("/", 1)[-1], 2027, 1)
    assert report.totals.current_amount == report.totals.previous_balance == 50
    assert report.totals.total_pending == 100
    assert report.services[0].provider_amount == report.services[0].amount == 50
    assert "Agua" in pdf_text(download(admin, paths[0], year=2027, month=1))
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Receipt)) == before


def test_admin_scope_two_owners_two_buildings_and_closed_session(
    admin, sign_in, portfolio, session_header
):
    assert "999,00" in pdf_text(download(admin, portfolio.paths[1]))
    unknown = f"/api/admin/buildings/{uuid4()}"
    assert download(admin, unknown).status_code == 404
    for owner in ("test-owner", "deadline-other"):
        assert sign_in(owner).status_code == 200
        for path in portfolio.paths + [unknown]:
            assert download(admin, path).status_code == 403
    assert admin.post("/api/auth/logout", headers=session_header).status_code == 204
    assert download(admin, portfolio.paths[0]).status_code == 401


@pytest.mark.parametrize(
    "query",
    [
        "billing_year=2019&billing_month=1",
        "billing_year=10000&billing_month=1",
        "billing_year=2027&billing_month=0",
        "billing_year=2027&billing_month=13",
        "billing_year=2027&billing_month=x",
        "billing_month=1",
        "billing_year=2027",
    ],
)
def test_period_validation(admin, portfolio, query):
    assert (
        admin.get(f"{portfolio.paths[0]}/consolidation.pdf?{query}").status_code == 422
    )


def test_empty_period_and_empty_building(admin, portfolio):
    assert download(admin, portfolio.paths[0], month=11).status_code == 409
    building = portfolio.post(
        "/api/admin/buildings", {"name": "Edificio vacío", "total_units": 0}
    )
    response = download(admin, f"/api/admin/buildings/{building['id']}")
    assert (
        response.status_code == 409 and "no tiene cargos" in response.json()["detail"]
    )


def test_pdf_escapes_text_and_paginates_long_names_and_amounts(portfolio, sessions):
    with sessions() as db:
        report = read_consolidation(db, portfolio.buildings[0]["id"], 2026, 12)
    report.building_name = "José & María <b> Torre de demostración"
    report.address = "Dirección sintética con acentos: ÁÉÍÓÚ, Ñ"
    report.units = [
        report.units[0].model_copy(
            update={
                "unit_number": f"Unidad larga {index:03} " + "AB" * 20,
                "owner_name": "María <b> & José " + "Familia de prueba " * 7,
                "current_amount": Decimal("9999999999.99"),
                "current_balance": Decimal("9999999999.99"),
            }
        )
        for index in range(35)
    ]
    body = render_consolidation(report)
    reader = PdfReader(BytesIO(body))
    assert len(reader.pages) >= 3
    pages = [page.extract_text() for page in reader.pages]
    contents = "\n".join(pages)
    assert "José & María <b>" in contents
    assert contents.count("9.999.999.999,99") == 105
    assert contents.count("349.999.999.999,65") == 6
    assert "000" in contents and "034" in contents
    assert contents.count("Unidad y propietario actual") > 1
    assert all(f"Página {index}" in contents for index in range(1, len(pages) + 1))


def test_parallel_rendering_keeps_each_building_separate(portfolio, sessions):
    with sessions() as db:
        report = read_consolidation(db, portfolio.buildings[0]["id"], 2026, 12)
    copies = [
        report.model_copy(update={"building_name": f"Edificio sintético {index}"})
        for index in range(4)
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        bodies = list(pool.map(render_consolidation, copies))
    for index, body in enumerate(bodies):
        contents = "\n".join(p.extract_text() for p in PdfReader(BytesIO(body)).pages)
        assert f"Edificio sintético {index}" in contents
        assert all(
            f"Edificio sintético {other}" not in contents
            for other in range(4)
            if other != index
        )


def test_report_holds_building_lock_until_all_financial_reads_finish(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        create_invoice(db, building, invoice_input(categories[0]), actor)
    data = PaymentInput(
        request_id=uuid4(),
        billing_year=2027,
        billing_month=1,
        amount="10.00",
        received_on="2027-01-07",
    )
    with Session(engine) as reader, Session(engine) as writer:
        report = read_consolidation(reader, building, 2027, 1)
        writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
        with pytest.raises(OperationalError) as error:
            record_payment(writer, building, unit, actor, data)
        assert error.value.orig.sqlstate == "55P03"
        writer.rollback()
        assert report.totals.total_pending == 50
        reader.rollback()
        record_payment(writer, building, unit, actor, data)
    with Session(engine) as db:
        assert read_consolidation(db, building, 2027, 1).totals.total_pending == 40
