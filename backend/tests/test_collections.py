import json
from urllib.parse import quote
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.collections.models import Payment, PaymentApplication
from app.collections.report_models import PaymentReport
from app.identity.models import Account, RoleName
from app.main import app
from app.storage.files import StorageUnavailable
from app.storage.s3 import storage_factory


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


def test_payment_period_is_a_reference_and_credit_covers_all_issued_charges(
    admin, session_header, ledger
):
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
    assert december.json()["credit"] == "0.00"
    assert [item["amount"] for item in december.json()["applications"]] == [
        "50.00",
        "10.00",
    ]
    exact = admin.post(
        f"{endpoint}/payments", headers=session_header, json=payment_data("50.00")
    )
    assert exact.status_code == 201
    assert exact.json()["credit"] == "10.00"
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


@pytest.fixture
def payment_storage():
    class MemoryProofs:
        fail = False

        def __init__(self):
            self.writes = []
            self.downloads = []

        def put(self, key, body, content_type):
            self.writes.append((key, body, content_type))
            if self.fail:
                raise StorageUnavailable("Almacenamiento de prueba no disponible.")

        def download_url(self, key, filename):
            assert key in {write[0] for write in self.writes}
            self.downloads.append((key, filename))
            return "https://proof.example.test/private"

    storage = MemoryProofs()
    app.dependency_overrides[storage_factory] = lambda: lambda: storage
    try:
        yield storage
    finally:
        del app.dependency_overrides[storage_factory]


def send_report(client, path, header, data, content=b"%PDF-1.7\nsynthetic proof"):
    metadata = quote(json.dumps(data, ensure_ascii=False), safe="")
    return client.post(
        path, headers={**header, "X-Edificios-Report": metadata}, content=content
    )


def test_approved_report_credit_applies_to_a_later_invoice_once(
    admin, ledger, session_header, sign_in, payment_storage, sessions
):
    (building, _), (unit_id, _), previous = ledger
    assert sign_in("test-owner").status_code == 200
    sent = send_report(
        admin,
        f"/api/owner/properties/{unit_id}/payment-reports",
        session_header,
        payment_data("110.00", filename="pago.pdf"),
    )
    assert sent.status_code == 201
    report = f"{building}/payment-reports/{sent.json()['id']}"
    assert sign_in("test-admin").status_code == 200
    approval = {"amount": "110.00", "received_on": "2027-01-08", "proof_revision": 0}
    assert (
        admin.put(
            f"{report}/approval", json=approval, headers=session_header
        ).status_code
        == 200
    )
    statement = f"{building}/units/{unit_id}/statement"
    assert admin.get(statement).json()["credit"] == "10.00"
    new = admin.post(
        f"{building}/invoices",
        headers=session_header,
        json={
            "category_id": previous[0]["category_id"],
            "billing_year": 2027,
            "billing_month": 2,
            "start_date": "2027-02-01",
            "end_date": "2027-02-25",
            "total_amount": "50.00",
            "total_volume": "1.000",
            "readings": [
                {
                    "unit_id": unit_id,
                    "previous_reading": "2.000",
                    "current_reading": "3.000",
                }
            ],
        },
    )
    assert new.status_code == 201, new.text
    assert (
        admin.put(
            f"{report}/approval", json=approval, headers=session_header
        ).status_code
        == 200
    )
    result = admin.get(statement).json()
    assert (result["balance"], result["credit"]) == ("40.00", "0.00")
    assert len(result["payments"]) == 1
    assert result["payments"][0]["applications"][-1]["automatic"] is True
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1


def test_payment_report_approval_is_atomic_idempotent_and_scoped(
    admin, ledger, session_header, sign_in, sessions, payment_storage
):
    (building, other), (unit_id, foreign_unit), invoices = ledger
    owner = f"/api/owner/properties/{unit_id}"
    path = f"{owner}/payment-reports"
    data = payment_data(filename="comprobante Perú.pdf", reference="Operación 01")
    assert sign_in("test-owner").status_code == 200
    assert send_report(admin, path, {}, data).status_code == 403
    first = send_report(admin, path, session_header, data)
    assert first.status_code == 201, first.text
    pending = first.json()
    assert pending["status"] == "PENDING"
    assert pending["filename"] == "comprobante Perú.pdf"
    assert pending["payment_id"] is None
    assert "storage_key" not in pending
    replay = send_report(admin, path, session_header, data)
    assert replay.status_code == 200 and replay.json() == pending
    assert (
        send_report(
            admin, path, session_header, {**data, "amount": "20.00"}
        ).status_code
        == 409
    )
    assert len(payment_storage.writes) == 1
    statement = admin.get(f"{owner}/statement").json()
    assert statement["balance"] == "100.00" and statement["payments"] == []

    proof = f"{path}/{pending['id']}/proof"
    download = admin.get(proof, follow_redirects=False)
    assert download.status_code == 303
    assert download.headers["Cache-Control"] == "no-store"
    assert sign_in("second-owner").status_code == 200
    assert admin.get(path).status_code == 404
    assert admin.get(proof, follow_redirects=False).status_code == 404
    assert (
        admin.get(
            proof.replace(unit_id, foreign_unit), follow_redirects=False
        ).status_code
        == 404
    )
    assert send_report(admin, path, session_header, data).status_code == 404

    assert sign_in("test-admin").status_code == 200
    collection = f"{building}/payment-reports"
    report = f"{collection}/{pending['id']}"
    assert admin.get(collection).json() == [pending]
    assert (
        admin.get(
            report.replace(building, other) + "/proof", follow_redirects=False
        ).status_code
        == 404
    )
    assert admin.get(f"{report}/proof", follow_redirects=False).status_code == 303
    assert (
        admin.get(f"{building}/invoices/{invoices[0]['id']}").json()[
            "accounting_locked"
        ]
        is True  # December was carried into January when the second invoice was issued.
    )
    confirmed = {
        "received_on": "2027-01-08",
        "amount": "12.00",
        "reference": "Operación 01",
    }
    wrong = admin.put(
        report.replace(building, other) + "/approval",
        headers=session_header,
        json=confirmed,
    )
    assert wrong.status_code == 404
    assert admin.put(f"{report}/approval", json=confirmed).status_code == 403
    response = admin.put(f"{report}/approval", headers=session_header, json=confirmed)
    assert response.status_code == 200, response.text
    approved = response.json()
    assert approved["status"] == "APPROVED"
    assert approved["amount"] == "10.00"
    assert (
        admin.put(f"{report}/approval", headers=session_header, json=confirmed).json()
        == approved
    )
    assert (
        admin.put(
            f"{report}/approval",
            headers=session_header,
            json={**confirmed, "amount": "13.00"},
        ).status_code
        == 409
    )
    assert (
        admin.put(
            f"{report}/rejection",
            headers=session_header,
            json={"reason": "Comprobante ilegible"},
        ).status_code
        == 409
    )
    assert (
        admin.get(f"{building}/invoices/{invoices[0]['id']}").json()[
            "accounting_locked"
        ]
        is True
    )
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1
        assert db.scalar(select(PaymentApplication.amount_cents)) == 1200
        assert (
            str(db.scalar(select(PaymentReport.payment_id))) == approved["payment_id"]
        )
    assert sign_in("test-owner").status_code == 200
    assert admin.get(path).json() == [approved]
    statement = admin.get(f"{owner}/statement").json()
    assert statement["balance"] == "88.00"
    assert statement["payments"][0]["id"] == approved["payment_id"]


def test_rejected_report_never_posts_and_failed_upload_can_retry(
    admin, ledger, session_header, sign_in, sessions, payment_storage, monkeypatch
):
    (building, _), (unit_id, _), _ = ledger
    path = f"/api/owner/properties/{unit_id}/payment-reports"
    assert sign_in("test-owner").status_code == 200
    data = payment_data(filename="comprobante.pdf")
    assert send_report(admin, path, session_header, data, b"<html>").status_code == 415
    monkeypatch.setattr("app.storage.http.MAX_FILE_BYTES", 25)
    assert send_report(admin, path, session_header, data, b"x" * 26).status_code == 413
    payment_storage.fail = True
    assert send_report(admin, path, session_header, data).status_code == 503
    assert admin.get(path).json() == []
    payment_storage.fail = False
    sent = send_report(admin, path, session_header, data)
    assert sent.status_code == 201
    assert payment_storage.writes[0] == payment_storage.writes[1]
    assert sign_in("test-admin").status_code == 200
    report = f"{building}/payment-reports/{sent.json()['id']}"
    reason = {"reason": "La referencia no coincide"}
    rejected = admin.put(f"{report}/rejection", headers=session_header, json=reason)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["payment_id"] is None
    assert (
        admin.put(f"{report}/rejection", headers=session_header, json=reason).json()
        == rejected.json()
    )
    response = admin.put(
        f"{report}/approval",
        headers=session_header,
        json={
            "received_on": "2027-01-07",
            "amount": "10.00",
        },
    )
    assert response.status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 0
    assert sign_in("test-owner").status_code == 200
    assert admin.get(path).json()[0]["rejection_reason"] == reason["reason"]


def test_replacing_proof_keeps_original_history_and_guards_stale_review(
    admin, ledger, session_header, sign_in, sessions, payment_storage
):
    (building, other), (unit_id, _), _ = ledger
    owner_path = f"/api/owner/properties/{unit_id}/payment-reports"
    assert sign_in("test-owner").status_code == 200
    original = send_report(
        admin, owner_path, session_header, payment_data(filename="original.pdf")
    ).json()
    report_path = f"{building}/payment-reports/{original['id']}"
    replacement = {
        "request_id": str(uuid4()),
        "filename": "legible.pdf",
        "reason": "Copia legible recibida por correo",
        "proof_revision": 0,
    }
    assert (
        send_report(
            admin, f"{report_path}/proofs", session_header, replacement
        ).status_code
        == 403
    )
    assert sign_in("test-admin").status_code == 200
    assert (
        send_report(
            admin,
            f"{report_path.replace(building, other)}/proofs",
            session_header,
            replacement,
        ).status_code
        == 404
    )
    response = send_report(
        admin,
        f"{report_path}/proofs",
        session_header,
        replacement,
        b"%PDF-1.7\nLegible",
    )
    assert response.status_code == 201, response.text
    current = response.json()
    assert current["proof_revision"] == 1 and current["status"] == "PENDING"
    assert current["filename"] == "original.pdf"
    assert (
        send_report(
            admin,
            f"{report_path}/proofs",
            session_header,
            replacement,
            b"%PDF-1.7\nLegible",
        ).status_code
        == 200
    )
    assert len(payment_storage.writes) == 2
    history = admin.get(f"{report_path}/proofs").json()
    assert [
        (item["revision"], item["filename"], item["uploaded_by"]) for item in history
    ] == [
        (0, "original.pdf", "test-owner"),
        (1, "legible.pdf", "test-admin"),
    ]
    assert history[0]["reason"] is None
    assert history[1]["reason"] == replacement["reason"]
    for revision, filename in ((0, "original.pdf"), (1, "legible.pdf")):
        assert (
            admin.get(
                f"{report_path}/proof",
                params={"revision": revision},
                follow_redirects=False,
            ).status_code
            == 303
        )
        assert payment_storage.downloads[-1][1] == filename
    assert payment_storage.downloads[-2][0] != payment_storage.downloads[-1][0]
    assert (
        admin.get(f"{report_path}/proof?revision=2", follow_redirects=False).status_code
        == 404
    )
    assert (
        admin.get(f"{report_path.replace(building, other)}/proofs").status_code == 404
    )
    approval = {"received_on": "2027-01-07", "amount": "10.00"}
    assert (
        admin.put(
            f"{report_path}/approval", headers=session_header, json=approval
        ).status_code
        == 409
    )
    assert (
        admin.put(
            f"{report_path}/rejection",
            headers=session_header,
            json={"reason": "Revisar"},
        ).status_code
        == 409
    )
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 0
    approved = admin.put(
        f"{report_path}/approval",
        headers=session_header,
        json={**approval, "proof_revision": 1},
    )
    assert approved.status_code == 200
    assert approved.json()["proof_revision"] == 1
    assert (
        send_report(
            admin,
            f"{report_path}/proofs",
            session_header,
            {**replacement, "request_id": str(uuid4()), "proof_revision": 1},
        ).status_code
        == 409
    )
    assert sign_in("test-owner").status_code == 200
    own = f"{owner_path}/{original['id']}"
    assert admin.get(f"{own}/proofs").json() == history
    assert (
        admin.get(f"{own}/proof?revision=1", follow_redirects=False).status_code == 303
    )
    assert sign_in("second-owner").status_code == 200
    assert admin.get(f"{own}/proofs").status_code == 404
    assert (
        admin.get(f"{own}/proof?revision=1", follow_redirects=False).status_code == 404
    )


def test_replacement_rolls_back_after_storage_failure_and_reuses_object_key(
    admin, ledger, session_header, sign_in, payment_storage
):
    (building, _), (unit_id, _), _ = ledger
    owner = f"/api/owner/properties/{unit_id}/payment-reports"
    assert sign_in("test-owner").status_code == 200
    original = send_report(
        admin, owner, session_header, payment_data(filename="original.pdf")
    ).json()
    path = f"{building}/payment-reports/{original['id']}/proofs"
    assert sign_in("test-admin").status_code == 200
    data = {
        "request_id": str(uuid4()),
        "filename": "nuevo.pdf",
        "reason": "Copia legible",
        "proof_revision": 0,
    }
    assert (
        send_report(admin, path, session_header, {**data, "reason": " "}).status_code
        == 422
    )
    assert send_report(admin, path, session_header, data, b"<html>").status_code == 415
    payment_storage.fail = True
    assert send_report(admin, path, session_header, data).status_code == 503
    assert len(admin.get(path).json()) == 1
    payment_storage.fail = False
    response = send_report(admin, path, session_header, data)
    assert response.status_code == 201 and response.json()["proof_revision"] == 1
    assert payment_storage.writes[-2] == payment_storage.writes[-1]
    changed = send_report(
        admin, path, session_header, {**data, "reason": "Otro motivo"}
    )
    assert changed.status_code == 409
    stale = send_report(
        admin, path, session_header, {**data, "request_id": str(uuid4())}
    )
    assert stale.status_code == 409
    assert len(admin.get(path).json()) == 2
