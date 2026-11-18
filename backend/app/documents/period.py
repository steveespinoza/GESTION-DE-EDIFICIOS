from app.collections.schemas import Statement, StatementCharge


class EmptyPeriod(Exception):
    pass


def period_charges(
    statement: Statement, year: int, month: int
) -> tuple[list[StatementCharge], list[StatementCharge]]:
    """Current-period charges and older unpaid sources, without duplicating carries."""
    period = (year, month)
    current = [
        c for c in statement.charges if (c.billing_year, c.billing_month) == period
    ]
    if not current:
        raise EmptyPeriod("El periodo seleccionado no tiene cargos para esta unidad.")
    earlier = [
        c
        for c in statement.charges
        if (c.billing_year, c.billing_month) < period and c.balance > 0
    ]
    return current, earlier
