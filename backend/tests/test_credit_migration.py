"""Upgrade a populated previous schema without rewriting its financial amounts."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def test_upgrade_preserves_existing_payment_and_downgrade_protects_carries(
    engine, monkeypatch
):
    schema = "credit_migration_" + uuid4().hex
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    isolated = create_engine(url)
    config = Config("alembic.ini")
    actor, building, unit, category, invoice, charge, payment = [
        uuid4() for _ in range(7)
    ]
    params = {
        "actor": actor,
        "building": building,
        "unit": unit,
        "category": category,
        "invoice": invoice,
        "charge": charge,
        "payment": payment,
        "request": uuid4(),
    }
    try:
        command.upgrade(config, "0011_add_report_proof_versions")
        with isolated.begin() as db:
            db.execute(
                text(
                    "INSERT INTO accounts (id, username, full_name, password_hash, role_name) VALUES (:actor, 'migration-synthetic', 'Cuenta sintética', 'unused', 'SuperAdmin')"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO buildings (id, name, total_units) VALUES (:building, 'Migración', 1)"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO units (id, building_id, owner_id, number, area_sqm) VALUES (:unit, :building, :actor, '001', 50)"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO service_categories (id, building_id, name, calculation_type) VALUES (:category, :building, 'Cuota', 'LINEAR')"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO service_invoices (id, category_id, billing_year, billing_month, start_date, end_date, total_cents) VALUES (:invoice, :category, 2026, 12, '2026-12-01', '2026-12-25', 10000)"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO unit_charges (id, invoice_id, unit_id, unit_number, amount_cents) VALUES (:charge, :invoice, :unit, '001', 10000)"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO payments (id, unit_id, request_id, billing_year, billing_month, received_on, amount_cents, credit_cents, recorded_by_id) VALUES (:payment, :unit, :request, 2026, 12, '2026-12-20', 12000, 2000, :actor)"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO payment_applications (payment_id, charge_id, amount_cents) VALUES (:payment, :charge, 10000)"
                ),
                params,
            )
            original = db.execute(text("SELECT recorded_at FROM payments")).scalar_one()
        command.upgrade(config, "0012_automatic_credit_and_carry")
        with isolated.connect() as db:
            previous_application = db.execute(
                text(
                    "SELECT payment_id, charge_id, amount_cents, applied_at, applied_by_id, automatic FROM payment_applications"
                )
            ).one()
        command.upgrade(config, "head")
        with isolated.connect() as db:
            preserved = db.execute(
                text(
                    "SELECT payment_id, charge_id, amount_cents, applied_at, applied_by_id, automatic FROM payment_applications"
                )
            ).one()
            assert preserved == previous_application
            assert (
                db.execute(text("SELECT id FROM payment_applications")).scalar_one()
                is not None
            )
            # A previous backend can still insert an application without the new id.
            savepoint = db.begin_nested()
            generated = db.execute(
                text(
                    "INSERT INTO payment_applications (payment_id, charge_id, amount_cents) VALUES (:payment, :charge, 1) RETURNING id"
                ),
                params,
            ).scalar_one()
            assert generated is not None
            savepoint.rollback()
            assert db.execute(
                text("SELECT amount_cents, credit_cents FROM payments")
            ).one() == (12000, 2000)
            row = db.execute(
                text(
                    "SELECT amount_cents, applied_at, applied_by_id, automatic FROM payment_applications"
                )
            ).one()
            assert tuple(row) == (10000, original, actor, False)
            assert (
                db.execute(
                    text("SELECT count(*) FROM balance_carry_forwards")
                ).scalar_one()
                == 0
            )
        # A schema-only rollback remains available before any new ledger movement.
        command.downgrade(config, "0011_add_report_proof_versions")
        command.upgrade(config, "head")
        with isolated.begin() as db:
            db.execute(
                text(
                    "INSERT INTO balance_carry_forwards (charge_id, billing_year, billing_month, amount_cents, recorded_by_id) VALUES (:charge, 2027, 1, 1, :actor)"
                ),
                params,
            )
        with pytest.raises(DBAPIError, match="Preserve credit applications"):
            command.downgrade(config, "0011_add_report_proof_versions")
        with isolated.connect() as db:
            assert (
                db.execute(
                    text("SELECT amount_cents FROM balance_carry_forwards")
                ).scalar_one()
                == 1
            )
        adjustment = uuid4()
        with isolated.begin() as db:
            db.execute(
                text(
                    "INSERT INTO charge_adjustments (id, charge_id, request_id, revision, previous_cents, revised_cents, delta_cents, reason, recorded_by_id) VALUES (:adjustment, :charge, :request, 1, 10000, 9000, -1000, 'Corrección sintética', :actor)"
                ),
                {**params, "adjustment": adjustment},
            )
            db.execute(
                text(
                    "INSERT INTO payment_application_releases (application_id, adjustment_id, amount_cents) SELECT id, :adjustment, 1000 FROM payment_applications"
                ),
                {"adjustment": adjustment},
            )
            db.execute(text("UPDATE payments SET credit_cents = 3000"))
        with pytest.raises(DBAPIError, match="Preserve charge adjustments"):
            command.downgrade(config, "0012_automatic_credit_and_carry")
        with isolated.connect() as db:
            assert (
                db.execute(text("SELECT count(*) FROM charge_adjustments")).scalar_one()
                == 1
            )
            assert (
                db.execute(
                    text("SELECT amount_cents FROM payment_application_releases")
                ).scalar_one()
                == 1000
            )
    finally:
        isolated.dispose()
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
