from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def test_receipt_upgrade_preserves_previous_data_and_guards_downgrade(
    engine, monkeypatch
):
    schema = "receipt_migration_" + uuid4().hex
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    isolated = create_engine(url)
    config = Config("alembic.ini")
    ids = {
        key: uuid4()
        for key in (
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
        )
    }
    tables = (
        "unit_charges",
        "payments",
        "payment_applications",
        "collection_deadlines",
    )

    def snapshot(db):
        return {
            table: db.execute(
                text(
                    f"SELECT row_to_json(t)::text FROM {table} t ORDER BY row_to_json(t)::text"
                )
            )
            .scalars()
            .all()
            for table in tables
        }

    try:
        command.upgrade(config, "0014_collection_deadlines")
        with isolated.begin() as db:
            for statement in (
                "INSERT INTO accounts (id, username, full_name, password_hash, role_name) VALUES (:actor, 'migration-receipt', 'Cuenta sintética', 'unused', 'SuperAdmin')",
                "INSERT INTO buildings (id, name, total_units) VALUES (:building, 'Migración recibos', 1)",
                "INSERT INTO units (id, building_id, owner_id, number, area_sqm) VALUES (:unit, :building, :actor, '001', 50)",
                "INSERT INTO service_categories (id, building_id, name, calculation_type) VALUES (:category, :building, 'Cuota', 'LINEAR')",
                "INSERT INTO service_invoices (id, category_id, billing_year, billing_month, start_date, end_date, total_cents) VALUES (:invoice, :category, 2026, 12, '2026-12-01', '2026-12-25', 10001)",
                "INSERT INTO unit_charges (id, invoice_id, unit_id, unit_number, amount_cents) VALUES (:charge, :invoice, :unit, '001', 10001)",
                "INSERT INTO payments (id, unit_id, request_id, billing_year, billing_month, received_on, amount_cents, credit_cents, recorded_by_id) VALUES (:payment, :unit, :request, 2026, 12, '2026-12-25', 1000, 0, :actor)",
                "INSERT INTO payment_applications (id, payment_id, charge_id, amount_cents) VALUES (:application, :payment, :charge, 1000)",
                "INSERT INTO collection_deadlines (id, building_id, billing_year, billing_month, revision, request_id, due_date, reason, recorded_by_id) VALUES (:deadline, :building, 2026, 12, 1, :request, '2027-01-10', 'Fecha de prueba', :actor)",
            ):
                db.execute(text(statement), ids)
            before = snapshot(db)
        command.upgrade(config, "0015_versioned_receipts")
        with isolated.connect() as db:
            assert snapshot(db) == before
            assert db.scalar(text("SELECT count(*) FROM receipts")) == 0
        command.downgrade(config, "0014_collection_deadlines")
        command.upgrade(config, "0015_versioned_receipts")
        with isolated.begin() as db:
            db.execute(
                text(
                    "INSERT INTO receipts (id, unit_id, request_id, billing_year, billing_month, version, reason, issued_by_id, issued_at, snapshot, filename, storage_key, size_bytes, sha256) VALUES (:receipt, :unit, :request, 2026, 12, 1, 'Emisión sintética', :actor, now(), jsonb_build_object('schema_version', 1), 'recibo.pdf', 'receipts/test.pdf', 8, repeat('0', 64))"
                ),
                ids,
            )
        with pytest.raises(DBAPIError, match="Preserve issued receipts"):
            command.downgrade(config, "0014_collection_deadlines")
        with isolated.connect() as db:
            assert snapshot(db) == before
            assert db.scalar(text("SELECT count(*) FROM receipts")) == 1
            assert (
                db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0015_versioned_receipts"
            )
    finally:
        isolated.dispose()
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
