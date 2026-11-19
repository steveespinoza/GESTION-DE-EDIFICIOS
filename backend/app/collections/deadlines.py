from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.deadline_schemas import DeadlineDetail, DeadlineInput
from app.collections.models import CollectionDeadline
from app.identity.models import Account
from app.properties.service import lock_building


class DeadlineConflict(Exception):
    pass


class BuildingNotFound(Exception):
    pass


def business_today() -> date:
    return datetime.now(ZoneInfo("America/Lima")).date()


def is_overdue(balance, due_date: date | None, as_of: date) -> bool:
    return balance > 0 and due_date is not None and due_date < as_of


def deadline_history(db: Session, building_id: UUID) -> list[DeadlineDetail]:
    return [
        DeadlineDetail(
            id=deadline.id,
            billing_year=deadline.billing_year,
            billing_month=deadline.billing_month,
            revision=deadline.revision,
            due_date=deadline.due_date,
            reason=deadline.reason,
            recorded_by=author,
            recorded_at=deadline.recorded_at.astimezone(UTC),
        )
        for deadline, author in db.execute(
            select(CollectionDeadline, Account.username)
            .join(Account, Account.id == CollectionDeadline.recorded_by_id)
            .where(CollectionDeadline.building_id == building_id)
            .order_by(
                CollectionDeadline.billing_year.desc(),
                CollectionDeadline.billing_month.desc(),
                CollectionDeadline.revision.desc(),
            )
        )
    ]


def current_dates(history: list[DeadlineDetail]) -> dict[tuple[int, int], date]:
    dates = {}
    for deadline in history:  # History is ordered with the latest revision first.
        dates.setdefault(
            (deadline.billing_year, deadline.billing_month), deadline.due_date
        )
    return dates


def record_deadline(
    db: Session, building_id: UUID, actor_id: UUID, data: DeadlineInput
) -> tuple[DeadlineDetail, bool]:
    if lock_building(db, building_id) is None:
        raise BuildingNotFound
    detail, created = stage_deadline(db, building_id, actor_id, data)
    if created:
        db.commit()
    return detail, created


def stage_deadline(
    db: Session, building_id: UUID, actor_id: UUID, data: DeadlineInput
) -> tuple[DeadlineDetail, bool]:
    """Caller holds the exclusive building lock and commits the whole operation."""
    history = deadline_history(db, building_id)
    existing = db.scalar(
        select(CollectionDeadline).where(
            CollectionDeadline.building_id == building_id,
            CollectionDeadline.request_id == data.request_id,
        )
    )
    if existing is not None:
        if (
            existing.billing_year,
            existing.billing_month,
            existing.revision,
            existing.due_date,
            existing.reason,
        ) != (
            data.billing_year,
            data.billing_month,
            data.revision + 1,
            data.due_date,
            data.reason,
        ):
            raise DeadlineConflict("La solicitud ya se utilizó con otros datos.")
        return next(item for item in history if item.id == existing.id), False
    current = next(
        (
            item
            for item in history
            if (item.billing_year, item.billing_month)
            == (data.billing_year, data.billing_month)
        ),
        None,
    )
    if data.revision != (current.revision if current else 0):
        raise DeadlineConflict(
            "El vencimiento cambió. Actualiza la página antes de guardar."
        )
    if current and current.due_date == data.due_date:
        raise DeadlineConflict("La fecha ya coincide con el vencimiento vigente.")
    entry = CollectionDeadline(
        building_id=building_id,
        recorded_by_id=actor_id,
        **data.model_dump(exclude={"revision"}),
        revision=data.revision + 1,
    )
    db.add(entry)
    db.flush()
    detail = next(
        item for item in deadline_history(db, building_id) if item.id == entry.id
    )
    return detail, True
