from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from uuid import uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_credit_concurrency import committed_portfolio as committed_data
from test_credit_concurrency import invoice_input
from test_deadlines import portfolio as deadline_portfolio
from test_invoice_attachments import MemoryStorage
from test_invoice_attachments import storage as memory_storage

from app.billing.invoices import create_invoice
from app.collections.models import CollectionDeadline
from app.documents import batches
from app.documents.batch_schemas import BatchInput
from app.documents.models import Receipt, ReceiptBatch, ReceiptBatchItem
from app.properties.models import Building
from app.storage.files import StorageUnavailable

portfolio = deadline_portfolio
storage = memory_storage
committed_portfolio = committed_data


def values(**overrides):
    return {
        "request_id": str(uuid4()),
        "billing_year": 2027,
        "billing_month": 2,
        "due_date": "2027-02-28",
        "deadline_revision": 0,
        "reason": "Emisión mensual por lote",
        **overrides,
    }


def endpoint(portfolio, index=0):
    return f"{portfolio.paths[index]}/receipt-batches"


def prepare(admin, portfolio, session_header, **overrides):
    response = admin.post(
        endpoint(portfolio), json=values(**overrides), headers=session_header
    )
    assert response.status_code == 201, response.text
    return response.json()


def issue(admin, portfolio, batch, unit, session_header):
    response = admin.post(
        f"{endpoint(portfolio)}/{batch['id']}/items/{unit}/issue",
        headers=session_header,
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_partial_success_retry_and_reload_keep_receipts_and_audit(
    admin, portfolio, session_header, sessions, storage, monkeypatch
):
    portfolio.pay("10.00")
    batch = prepare(admin, portfolio, session_header)
    assert batch["pending"] == 2 and batch["issued"] == 0
    original_put = storage.put

    def selective_failure(key, body, content_type):
        if portfolio.units[1] in key:
            raise StorageUnavailable("Synthetic failure")
        original_put(key, body, content_type)

    monkeypatch.setattr(storage, "put", selective_failure)
    first = issue(admin, portfolio, batch, portfolio.units[0], session_header)
    receipt = first["items"][0]["receipt"]
    failed = issue(admin, portfolio, batch, portfolio.units[1], session_header)
    assert (failed["issued"], failed["failed"], failed["pending"]) == (1, 1, 0)
    assert failed["items"][1]["retryable"]
    assert failed["items"][1]["attempts"] == 1
    assert failed["items"][1]["error_code"] == "STORAGE"
    assert admin.get(f"{endpoint(portfolio)}/{batch['id']}").json() == failed
    assert issue(admin, portfolio, batch, portfolio.units[0], session_header) == failed
    assert len(storage.put_keys) == 1
    monkeypatch.setattr(storage, "put", original_put)
    completed = issue(admin, portfolio, batch, portfolio.units[1], session_header)
    assert (completed["issued"], completed["failed"]) == (2, 0)
    assert completed["items"][0]["receipt"] == receipt
    assert completed["items"][0]["attempts"] == 1
    assert completed["items"][1]["attempts"] == 2
    assert completed["items"][1]["error_message"] is None
    assert all(item["last_attempt_by"] == "test-admin" for item in completed["items"])
    assert admin.get(endpoint(portfolio)).json()[0]["issued"] == 2
    for item in completed["items"]:
        assert item["receipt"]["due_date"] == "2027-02-28"
        statement = admin.get(
            f"{portfolio.paths[0]}/units/{item['unit_id']}/statement"
        ).json()
        assert item["receipt"]["total_pending"] == statement["balance"]
    with sessions() as db:
        records = db.scalars(select(Receipt)).all()
        assert len(records) == 2 and all(r.version == 1 for r in records)
        for record in records:
            body, content_type = storage.saved[record.storage_key]
            assert content_type == "application/pdf"
            contents = "\n".join(
                p.extract_text() for p in PdfReader(BytesIO(body)).pages
            )
            assert "28/02/2027" in contents and "Versión 1" in contents


def test_preparation_replays_before_deadline_checks_and_rejects_changed_payload(
    admin, portfolio, session_header, sessions
):
    data = values()
    first = admin.post(endpoint(portfolio), json=data, headers=session_header)
    assert first.status_code == 201
    again = admin.post(endpoint(portfolio), json=data, headers=session_header)
    assert again.status_code == 200 and again.json() == first.json()
    for change in (
        {"reason": "Otro motivo"},
        {"billing_month": 12},
        {"due_date": "2027-03-01"},
        {"deadline_revision": 1},
    ):
        assert (
            admin.post(
                endpoint(portfolio), json={**data, **change}, headers=session_header
            ).status_code
            == 409
        )
    assert (
        admin.post(
            endpoint(portfolio), json=values(), headers=session_header
        ).status_code
        == 409
    )
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ReceiptBatch)) == 1
        assert db.scalar(select(func.count()).select_from(CollectionDeadline)) == 1


def test_existing_deadline_is_reused_and_empty_period_does_not_change_dates(
    admin, portfolio, session_header, sessions
):
    assert (
        portfolio.deadline(year=2027, month=2, due="2027-02-28")[0].status_code == 201
    )
    batch = prepare(admin, portfolio, session_header, deadline_revision=1)
    assert batch["deadline_revision"] == 1
    assert (
        admin.post(
            endpoint(portfolio), json=values(billing_month=1), headers=session_header
        ).status_code
        == 409
    )
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CollectionDeadline)) == 1


def test_changed_receipt_requires_new_batch_and_new_versions_preserve_previous(
    admin, portfolio, session_header, storage, sessions
):
    batch = prepare(admin, portfolio, session_header)
    unit = portfolio.units[0]
    own = f"{portfolio.paths[0]}/units/{unit}/receipts"
    response = admin.post(
        own,
        json={
            "request_id": str(uuid4()),
            "billing_year": 2027,
            "billing_month": 2,
            "revision": 0,
            "reason": "Emisión individual posterior",
        },
        headers=session_header,
    )
    assert response.status_code == 201
    original = response.json()
    failed = issue(admin, portfolio, batch, unit, session_header)
    item = failed["items"][0]
    assert item["status"] == "FAILED" and item["error_code"] == "CONFLICT"
    assert not item["retryable"]
    assert issue(admin, portfolio, batch, unit, session_header) == failed
    second = prepare(
        admin,
        portfolio,
        session_header,
        deadline_revision=1,
        reason="Regeneración aprobada del mes",
    )
    assert second["items"][0]["revision"] == 1
    emitted = issue(admin, portfolio, second, unit, session_header)
    assert emitted["items"][0]["receipt"]["version"] == 2
    assert admin.get(own).json()[-1] == original
    with sessions() as db:
        assert len(db.scalars(select(Receipt)).all()) == 2


def test_deadline_change_preserves_success_and_stops_remaining_units(
    admin, portfolio, session_header, storage
):
    batch = prepare(admin, portfolio, session_header)
    first = issue(admin, portfolio, batch, portfolio.units[0], session_header)
    original = first["items"][0]["receipt"]
    assert (
        portfolio.deadline(year=2027, month=2, due="2027-03-03", revision=1)[
            0
        ].status_code
        == 201
    )
    failed = issue(admin, portfolio, batch, portfolio.units[1], session_header)
    assert failed["failed"] == failed["issued"] == 1
    assert failed["items"][1]["error_code"] == "CONFLICT"
    assert (
        issue(admin, portfolio, batch, portfolio.units[0], session_header)["items"][0][
            "receipt"
        ]
        == original
    )
    assert original["due_date"] == "2027-02-28" and len(storage.put_keys) == 1


def test_cohort_keeps_units_without_charges_and_excludes_later_additions(
    admin, portfolio, session_header, sessions, storage
):
    with sessions.begin() as db:
        db.get(Building, portfolio.buildings[0]["id"]).total_units = 4
    owner = admin.get("/api/admin/owners").json()[0]["id"]

    def add(number):
        return portfolio.post(
            f"{portfolio.paths[0]}/units",
            {
                "number": number,
                "area_sqm": "40",
                "owner": {"kind": "existing", "id": owner},
            },
        )

    skipped = add("003")
    batch = prepare(admin, portfolio, session_header)
    later = add("004")
    assert batch["skipped"] == 1 and batch["pending"] == 2
    assert issue(admin, portfolio, batch, skipped["id"], session_header) == batch
    assert storage.put_keys == []
    assert (
        admin.post(
            f"{endpoint(portfolio)}/{batch['id']}/items/{later['id']}/issue",
            headers=session_header,
        ).status_code
        == 404
    )


def test_role_building_batch_unit_and_mutation_header_scopes(
    admin, portfolio, sign_in, session_header, storage
):
    assert admin.get(endpoint(portfolio)).json() == []
    assert admin.post(endpoint(portfolio), json=values()).status_code == 403
    batch = prepare(admin, portfolio, session_header)
    path = f"{endpoint(portfolio)}/{batch['id']}"
    issue_path = f"{path}/items/{portfolio.units[0]}/issue"
    assert admin.post(issue_path).status_code == 403
    assert admin.get(f"{endpoint(portfolio, 1)}/{batch['id']}").status_code == 404
    assert (
        admin.post(
            f"{endpoint(portfolio, 1)}/{batch['id']}/items/{portfolio.units[0]}/issue",
            headers=session_header,
        ).status_code
        == 404
    )
    assert (
        admin.post(
            f"{path}/items/{portfolio.units[2]}/issue", headers=session_header
        ).status_code
        == 404
    )
    assert admin.get(f"{endpoint(portfolio)}/{uuid4()}").status_code == 404
    assert (
        admin.get(f"/api/admin/buildings/{uuid4()}/receipt-batches").status_code == 404
    )
    for owner in ("test-owner", "deadline-other"):
        assert sign_in(owner).status_code == 200
        assert admin.get(endpoint(portfolio)).status_code == 403
        assert admin.get(path).status_code == 403
        assert admin.post(issue_path, headers=session_header).status_code == 403
        assert (
            admin.post(
                endpoint(portfolio), json=values(), headers=session_header
            ).status_code
            == 403
        )
    assert admin.post("/api/auth/logout", headers=session_header).status_code == 204
    assert admin.get(path).status_code == 401
    assert storage.put_keys == []


@pytest.mark.parametrize(
    "override",
    [
        {"billing_year": 2019},
        {"billing_month": 13},
        {"deadline_revision": -1},
        {"reason": " "},
        {"reason": "x" * 501},
        {"due_date": "invalid"},
        {"unexpected": True},
    ],
)
def test_invalid_batch_input(admin, portfolio, session_header, override):
    assert (
        admin.post(
            endpoint(portfolio), json=values(**override), headers=session_header
        ).status_code
        == 422
    )


def test_unexpected_generation_failure_is_safe_and_retryable(
    admin, portfolio, session_header, storage, monkeypatch
):
    batch = prepare(admin, portfolio, session_header)
    real = batches.stage_receipt

    def fail(*args, **kwargs):
        raise ValueError("Internal implementation details")

    monkeypatch.setattr(batches, "stage_receipt", fail)
    failed = issue(admin, portfolio, batch, portfolio.units[0], session_header)
    assert failed["items"][0]["error_code"] == "GENERATION"
    assert failed["items"][0]["retryable"]
    assert "Internal implementation" not in str(failed)
    monkeypatch.setattr(batches, "stage_receipt", real)
    assert (
        issue(admin, portfolio, batch, portfolio.units[0], session_header)["issued"]
        == 1
    )


def test_receipt_and_item_result_rollback_together_on_database_failure(
    admin, portfolio, session_header, sessions, storage, monkeypatch
):
    batch = prepare(admin, portfolio, session_header)
    real = batches.stage_receipt

    def fail_after_receipt(*args, **kwargs):
        real(*args, **kwargs)
        raise SQLAlchemyError("Synthetic transaction failure")

    monkeypatch.setattr(batches, "stage_receipt", fail_after_receipt)
    with pytest.raises(SQLAlchemyError):
        issue(admin, portfolio, batch, portfolio.units[0], session_header)
    persisted = admin.get(f"{endpoint(portfolio)}/{batch['id']}").json()
    assert persisted["pending"] == 2 and persisted["issued"] == 0
    assert persisted["items"][0]["attempts"] == 0
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Receipt)) == 0
    monkeypatch.setattr(batches, "stage_receipt", real)
    assert (
        issue(admin, portfolio, batch, portfolio.units[0], session_header)["issued"]
        == 1
    )


def test_concurrent_preparation_and_issuance_have_one_effect(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio
    storage = MemoryStorage()
    with Session(engine) as db:
        create_invoice(db, building, invoice_input(categories[0]), actor)
    data = BatchInput(**values(billing_month=1))
    barrier = Barrier(2)

    def prepare_one():
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            return batches.prepare_batch(db, building, actor, data)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: prepare_one(), range(2)))
    assert results[0].id == results[1].id
    barrier = Barrier(2)

    def issue_one():
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            return batches.issue_item(
                db, building, results[0].id, unit, actor, lambda: storage
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        emitted = list(pool.map(lambda _: issue_one(), range(2)))
    assert emitted[0].items[0].receipt.id == emitted[1].items[0].receipt.id
    assert len(storage.put_keys) == 1
    with Session(engine) as db:
        item = db.get(ReceiptBatchItem, (results[0].id, unit))
        assert item.attempts == 1
        assert (
            db.scalar(
                select(func.count()).select_from(Receipt).where(Receipt.unit_id == unit)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ReceiptBatch)
                .where(ReceiptBatch.building_id == building)
            )
            == 1
        )
