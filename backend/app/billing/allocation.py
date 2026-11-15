def split_linear(total_cents: int, unit_count: int) -> list[int]:
    if total_cents <= 0 or unit_count <= 0:
        raise ValueError("A positive total and at least one unit are required.")

    quotient, remainder = divmod(total_cents, unit_count)
    return [quotient + int(index < remainder) for index in range(unit_count)]
