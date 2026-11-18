from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.billing import invoices
from app.billing.adjustment_schemas import ChargeAdjustmentInput
from app.billing.adjustments import adjust_charge
from app.billing.errors import InvoiceConflict
from app.billing.invoice_schemas import LinearInvoiceInput
from app.billing.models import (
    CalculationType,
    ChargeAdjustment,
    ServiceCategory,
    ServiceInvoice,
    UnitCharge,
)
from app.collections.deadline_schemas import DeadlineInput
from app.collections.deadlines import DeadlineConflict, record_deadline
from app.collections.models import (
    BalanceCarryForward,
    CollectionDeadline,
    Payment,
    PaymentApplication,
    PaymentApplicationRelease,
)
from app.collections.schemas import PaymentInput
from app.collections.service import read_statement, record_payment
from app.documents.models import Receipt
from app.documents.schemas import ReceiptInput
from app.documents.service import ReceiptConflict, issue_receipt
from app.identity.models import Account, RoleName
from app.properties.models import Building, Unit


@pytest.fixture
def committed_portfolio(engine, test_password_hash):
    building_id, owner_id, unit_id = uuid4(), uuid4(), uuid4()
    categories = [uuid4() for _ in range(3)]
    with Session(engine) as db, db.begin():
        db.add(
            Account(
                id=owner_id,
                username=f"credit-race-{owner_id}",
                full_name="Cuenta sintética",
                role_name=RoleName.SUPERADMIN,
                password_hash=test_password_hash,
            )
        )
        db.add(Building(id=building_id, name="Concurrencia de créditos", total_units=1))
        db.flush()
        db.add(
            Unit(
                id=unit_id,
                building_id=building_id,
                owner_id=owner_id,
                number="001",
                area_sqm=Decimal(50),
            )
        )
        db.add_all(
            ServiceCategory(
                id=category,
                building_id=building_id,
                name=f"Cuota {i}",
                calculation_type=CalculationType.LINEAR,
            )
            for i, category in enumerate(categories)
        )
    try:
        yield building_id, owner_id, unit_id, categories
    finally:
        with Session(engine) as db, db.begin():
            charges = select(UnitCharge.id).where(UnitCharge.unit_id == unit_id)
            payments = select(Payment.id).where(Payment.unit_id == unit_id)
            applications = select(PaymentApplication.id).where(
                PaymentApplication.payment_id.in_(payments)
            )
            db.execute(
                delete(PaymentApplicationRelease).where(
                    PaymentApplicationRelease.application_id.in_(applications)
                )
            )
            db.execute(
                delete(ChargeAdjustment).where(ChargeAdjustment.charge_id.in_(charges))
            )
            db.execute(
                delete(BalanceCarryForward).where(
                    BalanceCarryForward.charge_id.in_(charges)
                )
            )
            db.execute(
                delete(PaymentApplication).where(
                    PaymentApplication.payment_id.in_(payments)
                )
            )
            db.execute(delete(Payment).where(Payment.unit_id == unit_id))
            db.execute(delete(UnitCharge).where(UnitCharge.unit_id == unit_id))
            db.execute(
                delete(ServiceInvoice).where(ServiceInvoice.category_id.in_(categories))
            )
            db.execute(
                delete(ServiceCategory).where(ServiceCategory.id.in_(categories))
            )
            db.execute(delete(Receipt).where(Receipt.unit_id == unit_id))
            db.execute(delete(Unit).where(Unit.id == unit_id))
            db.execute(
                delete(CollectionDeadline).where(
                    CollectionDeadline.building_id == building_id
                )
            )
            db.execute(delete(Building).where(Building.id == building_id))
            db.execute(delete(Account).where(Account.id == owner_id))


def invoice_input(category, month=1, year=2027, amount="50.00"):
    return LinearInvoiceInput(
        category_id=category,
        billing_year=year,
        billing_month=month,
        start_date=f"{year}-{month:02}-01",
        end_date=f"{year}-{month:02}-25",
        total_amount=amount,
    )


def test_simultaneous_invoice_and_payment_reconcile_a_single_credit_pool(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio

    def payment(amount):
        return PaymentInput(
            request_id=uuid4(),
            billing_year=2026,
            billing_month=12,
            amount=amount,
            received_on="2026-12-20",
        )

    with Session(engine) as db:
        record_payment(db, building, unit, actor, payment("60.00"))
    barrier = Barrier(2)
    data = payment("10.00")

    def run(operation):
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            if operation == "invoice":
                invoices.create_invoice(
                    db, building, invoice_input(categories[0]), actor
                )
            else:
                record_payment(db, building, unit, actor, data)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, kind) for kind in ("invoice", "payment")]
        for future in futures:
            future.result(timeout=20)
    with Session(engine) as db:
        record_payment(db, building, unit, actor, data)
        result = read_statement(db, unit, building_id=building)
        assert result.balance == 0 and result.credit == Decimal("20.00")
        assert len(result.payments) == 2
        for recorded in result.payments:
            assert (
                sum(item.amount for item in recorded.applications) + recorded.credit
                == recorded.amount
            )
        assert (
            db.scalar(
                select(func.sum(PaymentApplication.amount_cents)).where(
                    PaymentApplication.charge_id.in_(
                        select(UnitCharge.id).where(UnitCharge.unit_id == unit)
                    )
                )
            )
            == 5000
        )


def test_simultaneous_period_invoices_record_one_carry_per_source_charge(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        original = invoices.create_invoice(
            db, building, invoice_input(categories[0], 12, 2026, "100.00"), actor
        )
    barrier = Barrier(2)

    def issue(category):
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            invoices.create_invoice(
                db, building, invoice_input(category, amount="10.00"), actor
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(issue, category) for category in categories[1:]]
        for future in futures:
            future.result(timeout=20)
    with Session(engine) as db:
        result = read_statement(db, unit, building_id=building)
        assert result.balance == Decimal("120.00")
        assert len(result.carry_forwards) == 1
        assert result.carry_forwards[0].amount == Decimal("100.00")
        assert db.get(ServiceInvoice, original.id).accounting_locked_at is not None


def test_simultaneous_repeated_payment_has_one_financial_effect(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        invoices.create_invoice(db, building, invoice_input(categories[0]), actor)
    data = PaymentInput(
        request_id=uuid4(),
        billing_year=2027,
        billing_month=1,
        amount="10.00",
        received_on="2027-01-10",
    )
    barrier = Barrier(2)

    def confirm():
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            return record_payment(db, building, unit, actor, data)[1]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(confirm) for _ in range(2)]
        assert sorted(future.result(timeout=20) for future in futures) == [False, True]
    with Session(engine) as db:
        result = read_statement(db, unit, building_id=building)
        assert result.balance == Decimal("40.00") and result.credit == 0
        assert len(result.payments) == 1
        assert [item.amount for item in result.payments[0].applications] == [
            Decimal("10.00")
        ]


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_adjustments_preserve_one_revision(
    engine, committed_portfolio, same_request
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        invoice = invoices.create_invoice(
            db, building, invoice_input(categories[0], amount="100.00"), actor
        )
        record_payment(
            db,
            building,
            unit,
            actor,
            PaymentInput(
                request_id=uuid4(),
                billing_year=2027,
                billing_month=1,
                amount="100.00",
                received_on="2027-01-10",
            ),
        )
    request_id = uuid4()
    barrier = Barrier(2)

    def adjust(index):
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            data = ChargeAdjustmentInput(
                request_id=request_id if same_request else uuid4(),
                revision=0,
                new_amount="80.00" if same_request or index == 0 else "70.00",
                reason="Corrección simultánea",
            )
            try:
                return adjust_charge(
                    db, building, invoice.id, invoice.charges[0].id, data, actor
                )[1]
            except InvoiceConflict:
                return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [executor.submit(adjust, index) for index in range(2)]
        assert sorted(attempt.result(timeout=20) for attempt in attempts) == [
            False,
            True,
        ]
    with Session(engine) as db:
        result = read_statement(db, unit, building_id=building)
        assert len(result.adjustments) == 1 and result.adjustments[0].revision == 1
        assert result.balance == 0
        assert result.credit == Decimal("100.00") - result.adjustments[0].new_amount
        assert sum(
            item.net_amount for item in result.payments[0].applications
        ) + result.credit == Decimal("100.00")


def test_adjustment_racing_with_payment_reconciles_the_original_charge(
    engine, committed_portfolio
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        invoice = invoices.create_invoice(
            db, building, invoice_input(categories[0], amount="100.00"), actor
        )
        record_payment(
            db,
            building,
            unit,
            actor,
            PaymentInput(
                request_id=uuid4(),
                billing_year=2027,
                billing_month=1,
                amount="100.00",
                received_on="2027-01-10",
            ),
        )
    barrier = Barrier(2)

    def run(operation):
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            if operation == "adjust":
                adjust_charge(
                    db,
                    building,
                    invoice.id,
                    invoice.charges[0].id,
                    ChargeAdjustmentInput(
                        request_id=uuid4(),
                        revision=0,
                        new_amount="120.00",
                        reason="Aumento del cargo",
                    ),
                    actor,
                )
            else:
                record_payment(
                    db,
                    building,
                    unit,
                    actor,
                    PaymentInput(
                        request_id=uuid4(),
                        billing_year=2027,
                        billing_month=1,
                        amount="10.00",
                        received_on="2027-01-11",
                    ),
                )

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [
            executor.submit(run, operation) for operation in ("adjust", "payment")
        ]
        for attempt in attempts:
            attempt.result(timeout=20)
    with Session(engine) as db:
        result = read_statement(db, unit, building_id=building)
        assert result.balance == Decimal("10.00") and result.credit == 0
        assert len(result.payments) == 2 and len(result.adjustments) == 1
        assert sum(payment.amount for payment in result.payments) == Decimal("110.00")
        assert sum(
            item.net_amount
            for payment in result.payments
            for item in payment.applications
        ) == Decimal("110.00")


@pytest.mark.parametrize("same_request", [True, False])
def test_simultaneous_deadlines_preserve_one_revision(
    engine, committed_portfolio, same_request
):
    building, actor, _, _ = committed_portfolio
    first = DeadlineInput(
        request_id=uuid4(),
        revision=0,
        billing_year=2026,
        billing_month=12,
        due_date="2027-01-10",
        reason="Acuerdo de prueba",
    )
    second = first if same_request else first.model_copy(update={"request_id": uuid4()})
    barrier = Barrier(2)

    def run(data):
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            try:
                detail, created = record_deadline(db, building, actor, data)
                return (str(detail.id), created)
            except DeadlineConflict:
                db.rollback()
                return ("conflict", False)

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [executor.submit(run, item) for item in (first, second)]
        results = [attempt.result(timeout=20) for attempt in attempts]
    assert sum(created for _, created in results) == 1
    if same_request:
        assert results[0][0] == results[1][0]
    else:
        assert sum(identifier == "conflict" for identifier, _ in results) == 1
    with Session(engine) as db:
        entries = db.scalars(
            select(CollectionDeadline).where(CollectionDeadline.building_id == building)
        ).all()
        assert len(entries) == 1 and entries[0].revision == 1


@pytest.mark.parametrize("same_request", [True, False])
def test_simultaneous_receipt_issuance_preserves_one_version(
    engine, committed_portfolio, same_request
):
    building, actor, unit, categories = committed_portfolio
    with Session(engine) as db:
        invoices.create_invoice(db, building, invoice_input(categories[0]), actor)
    request = ReceiptInput(
        request_id=uuid4(),
        billing_year=2027,
        billing_month=1,
        revision=0,
        reason="Emisión concurrente",
    )
    second = (
        request if same_request else request.model_copy(update={"request_id": uuid4()})
    )
    barrier = Barrier(2)

    class Files:
        def __init__(self):
            self.keys = []

        def put(self, key, body, content_type):
            self.keys.append(key)

    files = Files()

    def run(data):
        with Session(engine) as db:
            db.connection()
            barrier.wait(timeout=10)
            try:
                result, created = issue_receipt(
                    db, building, unit, actor, data, lambda: files
                )
                return str(result.id), created
            except ReceiptConflict:
                db.rollback()
                return "conflict", False

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [executor.submit(run, item) for item in (request, second)]
        results = [attempt.result(timeout=20) for attempt in attempts]
    assert sum(created for _, created in results) == 1
    assert len(files.keys) == 1
    if same_request:
        assert results[0][0] == results[1][0]
    else:
        assert sum(identifier == "conflict" for identifier, _ in results) == 1
    with Session(engine) as db:
        records = db.scalars(select(Receipt).where(Receipt.unit_id == unit)).all()
        assert len(records) == 1 and records[0].version == 1
