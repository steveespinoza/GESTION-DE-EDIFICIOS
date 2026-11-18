from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader
from sqlalchemy import func, select
from test_collections import ledger as metered_ledger
from test_invoice_attachments import storage as memory_storage

from app.collections.models import CollectionDeadline
from app.documents.models import Receipt
from app.documents.pdf import render_receipt
from app.documents.schemas import ReceiptSnapshot
from app.identity.models import Account
from app.properties.models import Building

ledger = metered_ledger
storage = memory_storage


def data(month=1, year=2027, revision=0, **overrides):
    return {
        "request_id": str(uuid4()),
        "billing_year": year,
        "billing_month": month,
        "revision": revision,
        "reason": "Emisión de prueba",
        **overrides,
    }


def endpoint(ledger):
    paths, units, _ = ledger
    return f"{paths[0]}/units/{units[0]}/receipts"


def issue(admin, ledger, session_header, **overrides):
    response = admin.post(
        endpoint(ledger), json=data(**overrides), headers=session_header
    )
    assert response.status_code == 201, response.text
    return response.json()


def pdf_record(sessions, storage, receipt_id):
    with sessions() as db:
        record = db.get(Receipt, receipt_id)
        snapshot = ReceiptSnapshot.model_validate(record.snapshot)
        body, content_type = storage.saved[record.storage_key]
        assert content_type == "application/pdf"
        assert record.size_bytes == len(body)
        return snapshot, body


def test_receipt_reconciles_metered_charges_payments_and_previous_balance(
    admin, ledger, session_header, sessions, storage
):
    paths, units, _ = ledger
    payment = admin.post(
        f"{paths[0]}/units/{units[0]}/payments",
        json={
            "request_id": str(uuid4()),
            "billing_year": 2027,
            "billing_month": 1,
            "received_on": "2027-01-07",
            "amount": "10.00",
        },
        headers=session_header,
    )
    assert payment.status_code == 201
    with sessions.begin() as db:
        actor = db.scalar(select(Account.id).where(Account.username == "test-admin"))
        db.add(
            CollectionDeadline(
                id=uuid4(),
                building_id=paths[0].split("/")[-1],
                billing_year=2027,
                billing_month=1,
                revision=1,
                request_id=uuid4(),
                due_date="2027-02-10",
                reason="Fecha de prueba",
                recorded_by_id=actor,
            )
        )
    receipt = issue(admin, ledger, session_header)
    assert receipt["version"] == 1 and receipt["total_pending"] == "90.00"
    assert receipt["due_date"] == "2027-02-10"
    snapshot, body = pdf_record(sessions, storage, receipt["id"])
    assert (
        str(snapshot.current_amount) == "50.00"
        and str(snapshot.current_applied) == "0.00"
    )
    assert (
        str(snapshot.current_balance) == "50.00"
        and str(snapshot.previous_balance) == "40.00"
    )
    assert len(snapshot.charges) == len(snapshot.previous_charges) == 1
    assert (
        snapshot.charges[0].consumption == 1
        and snapshot.charges[0].previous_reading == 1
        and snapshot.charges[0].current_reading == 2
    )
    assert snapshot.payments[0].amount == snapshot.payments[0].applied == 10
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(body)).pages)
    for expected in (
        "RECIBO DE COBRANZA",
        "enero de 2027",
        "Unidad",
        "90,00",
        "40,00",
        "10/02/2027",
        "Lecturas:",
        "1.000 a 2.000",
        "Pagos aplicados",
        "Versión 1",
    ):
        assert expected in text
    assert body.startswith(b"%PDF-")


def test_versions_preserve_emitted_amounts_dates_and_identity(
    admin, ledger, session_header, sessions, storage
):
    first = issue(admin, ledger, session_header)
    before, body = pdf_record(sessions, storage, first["id"])
    paths, units, _ = ledger
    payment = admin.post(
        f"{paths[0]}/units/{units[0]}/payments",
        json={
            "request_id": str(uuid4()),
            "billing_year": 2027,
            "billing_month": 1,
            "received_on": "2027-01-10",
            "amount": "110.00",
        },
        headers=session_header,
    )
    assert payment.status_code == 201
    with sessions.begin() as db:
        building = db.get(Building, paths[0].split("/")[-1])
        building.name = "Condominio <b> José & María"
        building.account_number = "123456789"
        actor = db.scalar(select(Account.id).where(Account.username == "test-admin"))
        db.add(
            CollectionDeadline(
                id=uuid4(),
                building_id=building.id,
                billing_year=2027,
                billing_month=1,
                revision=1,
                request_id=uuid4(),
                due_date=date(2027, 1, 31),
                reason="Vencimiento posterior a la primera emisión",
                recorded_by_id=actor,
            )
        )
    second = issue(
        admin, ledger, session_header, revision=1, reason="Actualizar tras pago"
    )
    after, new_body = pdf_record(sessions, storage, second["id"])
    assert (
        second["version"] == 2
        and second["total_pending"] == "0.00"
        and second["credit"] == "10.00"
    )
    assert pdf_record(sessions, storage, first["id"]) == (before, body)
    assert before.building_name == "Cedros" and before.total_pending == 100
    assert before.due_date is None and after.due_date == date(2027, 1, 31)
    assert after.building_name == "Condominio <b> José & María"
    assert after.payment_instructions.account_number == "123456789"
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(new_body)).pages)
    assert "Condominio <b> José & María" in text
    assert "10,00" in text
    listed = admin.get(endpoint(ledger)).json()
    assert [item["id"] for item in listed] == [second["id"], first["id"]]


def test_issuance_retry_and_stale_versions_have_one_effect(
    admin, ledger, session_header, storage, sessions
):
    request = data()
    first = admin.post(endpoint(ledger), json=request, headers=session_header)
    assert first.status_code == 201
    repeated = admin.post(endpoint(ledger), json=request, headers=session_header)
    assert repeated.status_code == 200 and repeated.json() == first.json()
    assert (
        admin.post(
            endpoint(ledger),
            json={**request, "reason": "Otro motivo"},
            headers=session_header,
        ).status_code
        == 409
    )
    assert (
        admin.post(endpoint(ledger), json=data(), headers=session_header).status_code
        == 409
    )
    assert len(storage.put_keys) == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Receipt)) == 1


def test_storage_failure_rolls_back_and_can_retry(
    admin, ledger, session_header, storage, sessions
):
    request = data()
    storage.fail_upload = True
    response = admin.post(endpoint(ledger), json=request, headers=session_header)
    assert response.status_code == 503
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Receipt)) == 0
    storage.fail_upload = False
    response = admin.post(endpoint(ledger), json=request, headers=session_header)
    assert response.status_code == 201 and response.json()["version"] == 1


def test_read_and_download_are_scoped_by_owner_building_unit_and_receipt(
    admin, sign_in, ledger, session_header, storage
):
    paths, units, _ = ledger
    receipt = issue(admin, ledger, session_header)
    pdf = f"{endpoint(ledger)}/{receipt['id']}/pdf"
    response = admin.get(pdf, follow_redirects=False)
    assert (
        response.status_code == 303
        and response.headers["location"] == "https://signed.example.test/file"
    )
    assert response.headers["cache-control"] == "no-store"
    assert admin.get(f"{paths[1]}/units/{units[0]}/receipts").status_code == 404
    assert (
        admin.get(
            f"{paths[1]}/units/{units[1]}/receipts/{receipt['id']}/pdf"
        ).status_code
        == 404
    )
    assert sign_in("test-owner").status_code == 200
    own = f"/api/owner/properties/{units[0]}/receipts"
    assert admin.get(own).json() == [receipt]
    assert (
        admin.get(f"{own}/{receipt['id']}/pdf", follow_redirects=False).status_code
        == 303
    )
    assert admin.get(endpoint(ledger)).status_code == 403
    assert (
        admin.post(endpoint(ledger), json=data(), headers=session_header).status_code
        == 403
    )
    downloads = len(storage.downloads)
    assert sign_in("second-owner").status_code == 200
    assert admin.get(own).status_code == 404
    assert (
        admin.get(f"{own}/{receipt['id']}/pdf", follow_redirects=False).status_code
        == 404
    )
    assert (
        admin.get(
            f"/api/owner/properties/{units[1]}/receipts/{receipt['id']}/pdf",
            follow_redirects=False,
        ).status_code
        == 404
    )
    assert len(storage.downloads) == downloads
    admin.cookies.clear()
    assert admin.get(own).status_code == 401
    assert admin.get(pdf, follow_redirects=False).status_code == 401


def test_invalid_periods_empty_history_and_mutation_header(
    admin, ledger, session_header, storage
):
    assert admin.get(endpoint(ledger)).json() == []
    assert admin.post(endpoint(ledger), json=data()).status_code == 403
    assert (
        admin.post(
            endpoint(ledger), json=data(month=8), headers=session_header
        ).status_code
        == 409
    )
    for override in (
        {"billing_month": 13},
        {"billing_year": 2019},
        {"revision": -1},
        {"reason": " "},
        {"reason": "x" * 501},
    ):
        assert (
            admin.post(
                endpoint(ledger), json=data(**override), headers=session_header
            ).status_code
            == 422
        )
    assert storage.put_keys == []


def test_receipt_excludes_later_period_charges(
    admin, ledger, session_header, storage, sessions
):
    paths, _, invoices = ledger
    response = admin.post(
        f"{paths[0]}/invoices",
        json={
            "category_id": invoices[0]["category_id"],
            "billing_year": 2027,
            "billing_month": 2,
            "start_date": "2027-02-01",
            "end_date": "2027-02-25",
            "total_amount": "50.00",
            "total_volume": "1.000",
            "readings": [
                {
                    "unit_id": ledger[1][0],
                    "previous_reading": "2",
                    "current_reading": "3",
                    "rollover_confirmed": False,
                }
            ],
        },
        headers=session_header,
    )
    assert response.status_code == 201
    receipt = issue(admin, ledger, session_header)
    snapshot, _ = pdf_record(sessions, storage, receipt["id"])
    assert snapshot.total_pending == 100
    assert all(
        (item.billing_year, item.billing_month) <= (2027, 1)
        for item in snapshot.charges + snapshot.previous_charges
    )


def test_parallel_pdf_rendering_keeps_each_snapshots_content(
    admin, ledger, session_header, storage, sessions
):
    receipt = issue(admin, ledger, session_header)
    snapshot, _ = pdf_record(sessions, storage, receipt["id"])
    copies = [
        snapshot.model_copy(update={"owner_name": f"Propietario sintético {index}"})
        for index in range(4)
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        documents = list(executor.map(render_receipt, copies))
    for index, document in enumerate(documents):
        text = "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(document)).pages
        )
        assert f"Propietario sintético {index}" in text
        assert all(
            f"Propietario sintético {other}" not in text
            for other in range(4)
            if other != index
        )
