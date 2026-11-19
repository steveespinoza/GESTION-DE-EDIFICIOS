from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError


def test_batch_migration_preserves_existing_finances_and_receipts(engine, monkeypatch):
    schema = "batch_migration_" + uuid4().hex
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    isolated = create_engine(url)
    config = Config("alembic.ini")
    ids = {
        name: uuid4()
        for name in (
            "actor",
            "building",
            "unit",
            "category",
            "invoice",
            "charge",
            "payment",
            "application",
            "deadline",
            "receipt",
            "request",
            "batch",
        )
    }

    def snapshot(db, names):
        return {
            name: db.execute(
                text(
                    f'SELECT row_to_json(t)::text FROM "{name}" t ORDER BY row_to_json(t)::text'
                )
            )
            .scalars()
            .all()
            for name in names
        }

    try:
        command.upgrade(config, "0015_versioned_receipts")
        with isolated.begin() as db:
            for sql in (
                "INSERT INTO accounts (id, username, full_name, password_hash, role_name) VALUES (:actor, 'batch-migration', 'Cuenta sintética', 'unused', 'SuperAdmin')",
                "INSERT INTO buildings (id, name, total_units) VALUES (:building, 'Migración de lotes', 1)",
                "INSERT INTO units (id, building_id, owner_id, number, area_sqm) VALUES (:unit, :building, :actor, '001', 50)",
                "INSERT INTO service_categories (id, building_id, name, calculation_type) VALUES (:category, :building, 'Cuota', 'LINEAR')",
                "INSERT INTO service_invoices (id, category_id, billing_year, billing_month, start_date, end_date, total_cents) VALUES (:invoice, :category, 2026, 12, '2026-12-01', '2026-12-25', 10001)",
                "INSERT INTO unit_charges (id, invoice_id, unit_id, unit_number, amount_cents) VALUES (:charge, :invoice, :unit, '001', 10001)",
                "INSERT INTO payments (id, unit_id, request_id, billing_year, billing_month, received_on, amount_cents, credit_cents, recorded_by_id) VALUES (:payment, :unit, :request, 2026, 12, '2026-12-25', 1000, 0, :actor)",
                "INSERT INTO payment_applications (id, payment_id, charge_id, amount_cents) VALUES (:application, :payment, :charge, 1000)",
                "INSERT INTO collection_deadlines (id, building_id, billing_year, billing_month, revision, request_id, due_date, reason, recorded_by_id) VALUES (:deadline, :building, 2026, 12, 1, :request, '2027-01-10', 'Fecha de prueba', :actor)",
                "INSERT INTO receipts (id, unit_id, request_id, billing_year, billing_month, version, reason, issued_by_id, issued_at, snapshot, filename, storage_key, size_bytes, sha256) VALUES (:receipt, :unit, :request, 2026, 12, 1, 'Recibo previo', :actor, now(), jsonb_build_object('schema_version', 1), 'previo.pdf', 'receipts/previo.pdf', 8, repeat('0', 64))",
            ):
                db.execute(text(sql), ids)
            names = (
                db.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema=:schema AND table_type='BASE TABLE' AND table_name <> 'alembic_version' ORDER BY table_name"
                    ),
                    {"schema": schema},
                )
                .scalars()
                .all()
            )
            before = snapshot(db, names)
        command.upgrade(config, "0016_receipt_batches")
        command.check(config)
        with isolated.connect() as db:
            assert snapshot(db, names) == before
            assert db.scalar(text("SELECT count(*) FROM receipt_batches")) == 0
            assert db.scalar(text("SELECT count(*) FROM receipt_batch_items")) == 0
        command.downgrade(config, "0015_versioned_receipts")
        command.upgrade(config, "0016_receipt_batches")
        with isolated.begin() as db:
            db.execute(
                text(
                    "INSERT INTO receipt_batches (id, building_id, request_id, billing_year, billing_month, due_date, deadline_id, base_deadline_revision, deadline_revision, reason, created_by_id) VALUES (:batch, :building, :request, 2026, 12, '2027-01-10', :deadline, 1, 1, 'Lote sintético', :actor)"
                ),
                ids,
            )
            db.execute(
                text(
                    "INSERT INTO receipt_batch_items (batch_id, unit_id, unit_number, revision, status, receipt_id, attempts, last_attempt_at, last_attempt_by_id) VALUES (:batch, :unit, '001', 0, 'ISSUED', :receipt, 1, now(), :actor)"
                ),
                ids,
            )
        for assignment in (
            "status='PENDING'",
            "status='FAILED'",
            "attempts=-1",
            "last_attempt_by_id=NULL",
        ):
            with pytest.raises(IntegrityError), isolated.begin() as db:
                db.execute(
                    text(
                        f"UPDATE receipt_batch_items SET {assignment} WHERE batch_id=:batch"
                    ),
                    ids,
                )
        with pytest.raises(IntegrityError), isolated.begin() as db:
            db.execute(
                text(
                    "INSERT INTO receipt_batches (id, building_id, request_id, billing_year, billing_month, due_date, deadline_id, base_deadline_revision, deadline_revision, reason, created_by_id) VALUES (:new, :building, :request, 2026, 12, '2027-01-10', :deadline, 1, 1, 'Duplicado', :actor)"
                ),
                {**ids, "new": uuid4()},
            )
        with pytest.raises(DBAPIError, match="Preserve receipt batches"):
            command.downgrade(config, "0015_versioned_receipts")
        with isolated.connect() as db:
            assert snapshot(db, names) == before
            assert db.scalar(text("SELECT count(*) FROM receipt_batch_items")) == 1
            assert (
                db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0016_receipt_batches"
            )
    finally:
        isolated.dispose()
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
