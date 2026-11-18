from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.billing.attachment_models import FileKind, InvoiceAttachment
from app.billing.models import InvoiceCorrection, ServiceInvoice, UnitCharge
from app.identity.models import Account
from app.properties.models import Unit


@pytest.fixture
def workspace(admin, session_header):
    def create(path, data):
        response = admin.post(path, json=data, headers=session_header)
        assert response.status_code == 201, response.text
        return response.json()

    buildings = "/api/admin/buildings"
    building = create(buildings, {"name": "Cedros", "total_units": 4})
    other = create(buildings, {"name": "Flores", "total_units": 1})
    path = f"{buildings}/{building['id']}"
    owner = admin.get("/api/admin/owners").json()[0]
    units = [
        create(
            f"{path}/units",
            {
                "number": number,
                "area_sqm": "40.00",
                "owner": {"kind": "existing", "id": owner["id"]},
            },
        )
        for number in ("001", "002", "003")
    ]
    return create, path, other["id"], units, owner["id"]


def issue(workspace, *, month=11, category=None, current=None, previous=None):
    create, path, _, units, _ = workspace
    if category is None:
        kind = "METERED" if current is not None else "LINEAR"
        category = create(
            f"{path}/services", {"name": "Servicio", "calculation_type": kind}
        )["id"]
    data = {
        "category_id": category,
        "billing_year": 2026,
        "billing_month": month,
        "start_date": f"2026-{month}-01",
        "end_date": f"2026-{month}-25",
        "total_amount": "100.00",
    }
    if current is not None:
        data["total_volume"] = "30.000"
        data["readings"] = [
            {
                "unit_id": unit["id"],
                "previous_reading": before,
                "current_reading": after,
            }
            for unit, before, after in zip(units, previous, current, strict=True)
        ]
    invoice = create(f"{path}/invoices", data)
    return f"{path}/invoices/{invoice['id']}", invoice


def correction(invoice, **updates):
    return {
        "revision": invoice["revision"],
        "reason": "Importe verificado con el proveedor",
        "start_date": invoice["start_date"],
        "end_date": invoice["end_date"],
        "total_amount": invoice["total_amount"],
        **updates,
    }


def test_linear_correction_preserves_original_charges_files_and_audit(
    admin, session_header, sessions, workspace
):
    path, original = issue(workspace)
    invoice_id = UUID(original["id"])
    create, building_path, _, units, owner_id = workspace
    create(
        f"{building_path}/units",
        {
            "number": "004",
            "area_sqm": "45.00",
            "owner": {"kind": "existing", "id": owner_id},
        },
    )
    charge_ids = select(UnitCharge.id).where(UnitCharge.invoice_id == invoice_id)
    with sessions.begin() as db:
        db.get(Unit, UUID(units[0]["id"])).number = "101"
        existing_charge_ids = set(db.scalars(charge_ids))
        db.add(
            InvoiceAttachment(
                invoice_id=invoice_id,
                kind=FileKind.DOCUMENT,
                filename="factura.pdf",
                content_type="application/pdf",
                size_bytes=10,
                sha256="0" * 64,
                storage_key=f"invoice-files/{invoice_id}/document/example",
            )
        )

    request = correction(original, total_amount="100.01", end_date="2026-11-26")
    saved = admin.put(path, json=request, headers=session_header)
    assert saved.status_code == 200, saved.text
    updated = saved.json()
    assert updated["id"] == original["id"]
    assert updated["billing_month"] == original["billing_month"]
    assert updated["revision"] == 1
    assert updated["end_date"] == "2026-11-26"
    assert [row["amount"] for row in updated["charges"]] == ["33.34", "33.34", "33.33"]
    assert [row["unit_number"] for row in updated["charges"]] == ["001", "002", "003"]
    assert updated["corrections"][0]["corrected_by"] == "test-admin"
    assert updated["corrections"][0]["reason"] == request["reason"]
    assert admin.get(path).json() == updated
    assert admin.get(f"{path}/attachments").json()[0]["filename"] == "factura.pdf"

    stale = admin.put(path, json=request, headers=session_header)
    assert stale.status_code == 409 and "Recarga la ficha" in stale.json()["detail"]
    same = admin.put(path, json=correction(updated), headers=session_header)
    assert same.json() == updated
    with sessions() as db:
        assert set(db.scalars(charge_ids)) == existing_charge_ids
        entry = db.scalars(select(InvoiceCorrection)).one()
        assert entry.corrected_by_id == db.scalar(
            select(Account.id).where(Account.username == "test-admin")
        )
        assert entry.before["total_amount"] == "100.00"
        assert entry.before["charges"][0]["amount"] == "33.34"
        assert entry.after["total_amount"] == "100.01"
        assert entry.after["charges"][1]["amount"] == "33.34"


def test_metered_correction_enforces_continuity_and_recalculates(
    admin, session_header, workspace
):
    path, original = issue(
        workspace, previous=("0", "0", "0"), current=("10", "5", "0")
    )
    following_path, following = issue(
        workspace,
        month=12,
        category=original["category_id"],
        previous=("10", "5", "0"),
        current=("12", "10", "4"),
    )
    # A carry freezes the original charges as well as a payment does.
    blocked = admin.put(path, json=correction(original), headers=session_header)
    assert (
        blocked.status_code == 409 and "requiere un ajuste" in blocked.json()["detail"]
    )
    readings = [
        {
            "unit_id": row["unit_id"],
            "previous_reading": row["meter"]["previous_reading"],
            "current_reading": row["meter"]["current_reading"],
        }
        for row in following["charges"]
    ]
    changed = [{**readings[0], "previous_reading": "11"}, *readings[1:]]
    for volume, inputs, detail in (
        ("20", changed, "lectura anterior"),
        ("10.999", readings, "supera el volumen"),
    ):
        invalid = correction(
            following, total_amount="100.01", total_volume=volume, readings=inputs
        )
        result = admin.put(following_path, json=invalid, headers=session_header)
        assert result.status_code == 409 and detail in result.json()["detail"]
    assert admin.get(following_path).json() == following
    request = correction(
        following, total_amount="100.01", total_volume="20", readings=readings
    )
    result = admin.put(following_path, json=request, headers=session_header)
    assert result.status_code == 200, result.text
    updated = result.json()
    assert updated["total_volume"] == "20.000"
    assert updated["common_volume"] == "9.000"
    assert updated["charges"][0]["meter"]["consumption"] == "2.000"
    assert sum(Decimal(row["amount"]) for row in updated["charges"]) == Decimal(
        "100.01"
    )
    assert admin.get(path).json() == {**original, "accounting_locked": True}


def test_correction_respects_accounting_lock_and_authorization(
    admin, session_header, sessions, workspace, sign_in
):
    path, original = issue(workspace)
    _, _, other_id, _, _ = workspace
    invoice_id = UUID(original["id"])
    request = correction(original, total_amount="200.00")
    other = f"/api/admin/buildings/{other_id}/invoices/{invoice_id}"
    assert admin.put(other, json=request, headers=session_header).status_code == 404
    assert admin.put(path, json=request).status_code == 403
    assert (
        admin.put(
            path, json={**request, "reason": "   "}, headers=session_header
        ).status_code
        == 422
    )
    assert (
        admin.put(
            path, json={**request, "billing_month": 12}, headers=session_header
        ).status_code
        == 422
    )

    with sessions.begin() as db:
        db.get(ServiceInvoice, invoice_id).accounting_locked_at = datetime.now(UTC)
    locked = admin.put(path, json=request, headers=session_header)
    assert locked.status_code == 409 and "requiere un ajuste" in locked.json()["detail"]
    assert admin.get(path).json() == {**original, "accounting_locked": True}
    assert sign_in("test-owner").status_code == 200
    assert admin.put(path, json=request, headers=session_header).status_code == 403
