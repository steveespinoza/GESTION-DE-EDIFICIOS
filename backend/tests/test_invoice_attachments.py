from datetime import date

import pytest

from app.billing.models import CalculationType, ServiceCategory, ServiceInvoice
from app.main import app
from app.properties.models import Building
from app.storage.files import StorageUnavailable
from app.storage.s3 import storage_factory

PDF = b"%PDF-1.7\nFixture document"
PNG = b"\x89PNG\r\n\x1a\nFixture photo"


class MemoryStorage:
    def __init__(self):
        self.saved = {}
        self.put_keys = []
        self.downloads = []
        self.fail_upload = False

    def put(self, key, body, content_type):
        self.saved[key] = (body, content_type)
        self.put_keys.append(key)
        if self.fail_upload:
            raise StorageUnavailable(
                "No se pudo guardar el archivo en el almacenamiento."
            )

    def download_url(self, key, filename):
        self.downloads.append((key, filename))
        return "https://signed.example.test/file"


@pytest.fixture
def storage():
    adapter = MemoryStorage()
    app.dependency_overrides[storage_factory] = lambda: lambda: adapter
    try:
        yield adapter
    finally:
        del app.dependency_overrides[storage_factory]


@pytest.fixture
def invoice_urls(sessions):
    with sessions.begin() as db:
        first = Building(name="Cedros", total_units=1)
        second = Building(name="Flores", total_units=1)
        db.add_all([first, second])
        db.flush()
        categories = [
            ServiceCategory(
                name="Servicios",
                building_id=first.id,
                calculation_type=CalculationType.LINEAR,
            ),
            ServiceCategory(
                name="Agua",
                building_id=second.id,
                calculation_type=CalculationType.METERED,
            ),
        ]
        db.add_all(categories)
        db.flush()
        invoices = [
            ServiceInvoice(
                category_id=category.id,
                billing_year=2026,
                billing_month=11,
                start_date=date(2026, 11, 1),
                end_date=date(2026, 11, 25),
                total_cents=10000,
                total_volume_milli=30_000 if index else None,
            )
            for index, category in enumerate(categories)
        ]
        db.add_all(invoices)
        db.flush()
        build = "/api/admin/buildings"
        own = f"{build}/{first.id}/invoices/{invoices[0].id}/attachments"
        other = f"{build}/{second.id}/invoices/{invoices[1].id}/attachments"
        wrong = f"{build}/{second.id}/invoices/{invoices[0].id}/attachments"
        return own, other, wrong


def upload(client, url, headers, kind="DOCUMENT", filename="factura.pdf", body=PDF):
    return client.post(
        url, params={"kind": kind, "filename": filename}, content=body, headers=headers
    )


def test_uploads_documents_and_single_voucher_and_downloads_after_reload(
    admin, session_header, invoice_urls, storage
):
    own, other, _ = invoice_urls
    assert admin.get(own).json() == []
    first = upload(admin, own, session_header)
    photo = upload(admin, own, session_header, filename="recibo.png", body=PNG)
    voucher = upload(admin, own, session_header, kind="VOUCHER", filename="pago.pdf")
    assert first.status_code == photo.status_code == voucher.status_code == 201
    assert len(storage.saved) == 3
    assert {item["id"]: item for item in admin.get(own).json()} == {
        response.json()["id"]: response.json() for response in (first, photo, voucher)
    }
    assert admin.get(other).json() == []
    assert set(first.json()) == {
        "id",
        "kind",
        "filename",
        "content_type",
        "size_bytes",
        "uploaded_at",
    }

    repeat = upload(admin, own, session_header)
    assert repeat.status_code == 200 and repeat.json() == first.json()
    assert len(storage.put_keys) == 3
    assert (
        upload(
            admin, own, session_header, kind="VOUCHER", filename="otro.png", body=PNG
        ).status_code
        == 409
    )
    assert upload(admin, other, session_header).status_code == 201

    result = admin.get(f"{own}/{first.json()['id']}/download", follow_redirects=False)
    assert result.status_code == 303
    assert result.headers["location"] == "https://signed.example.test/file"
    assert result.headers["cache-control"] == "no-store"
    assert storage.downloads == [(storage.put_keys[0], "factura.pdf")]


def test_only_superadmin_can_access_the_scoped_invoice_files(
    admin, sign_in, session_header, invoice_urls, storage
):
    own, other, wrong = invoice_urls
    created = upload(admin, own, session_header)
    attachment_id = created.json()["id"]
    for route in (
        wrong,
        f"{wrong}/{attachment_id}/download",
        f"{other}/{attachment_id}/download",
    ):
        assert admin.get(route, follow_redirects=False).status_code == 404
    assert upload(admin, wrong, session_header).status_code == 404
    assert admin.post("/api/auth/logout", headers=session_header).status_code == 204
    assert admin.get(own).status_code == 401
    assert sign_in("test-owner").status_code == 200
    assert admin.get(own).status_code == 403
    assert (
        admin.get(f"{own}/{attachment_id}/download", follow_redirects=False).status_code
        == 403
    )
    assert upload(admin, own, session_header).status_code == 403
    assert not storage.downloads
    assert len(storage.saved) == 1


def test_rejects_invalid_empty_and_oversized_uploads(
    admin, session_header, invoice_urls, storage, monkeypatch
):
    own, _, _ = invoice_urls
    assert (
        upload(
            admin, own, session_header, filename="falso.pdf", body=b"<!doctype html>"
        ).status_code
        == 415
    )
    assert (
        upload(admin, own, session_header, filename="../factura.pdf").status_code == 415
    )
    assert upload(admin, own, session_header, body=b"").status_code == 422
    assert upload(admin, own, {}).status_code == 403
    monkeypatch.setattr("app.storage.http.MAX_FILE_BYTES", 32)
    assert upload(admin, own, session_header, body=PDF + b"X" * 64).status_code == 413
    stream = iter((b"%PDF-", b"X" * 64))
    assert upload(admin, own, session_header, body=stream).status_code == 413
    assert admin.get(own).json() == []
    assert not storage.saved


def test_storage_error_rolls_back_metadata_and_retry_reuses_object_key(
    admin, session_header, invoice_urls, storage
):
    own, _, _ = invoice_urls
    storage.fail_upload = True
    assert upload(admin, own, session_header).status_code == 503
    assert admin.get(own).json() == []
    storage.fail_upload = False
    assert upload(admin, own, session_header).status_code == 201
    assert len(admin.get(own).json()) == 1
    assert storage.put_keys[0] == storage.put_keys[1]
    assert len(storage.saved) == 1
