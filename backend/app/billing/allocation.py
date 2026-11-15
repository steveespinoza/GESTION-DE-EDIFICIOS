def split_linear(total_cents: int, unit_count: int) -> list[int]:
    if total_cents <= 0 or unit_count <= 0:
        raise ValueError("A positive total and at least one unit are required.")

    quotient, remainder = divmod(total_cents, unit_count)
    return [quotient + int(index < remainder) for index in range(unit_count)]


def split_metered(
    total_cents: int, total_volume: int, consumptions: list[int]
) -> list[tuple[int, int]]:
    unit_count = len(consumptions)
    common = total_volume - sum(consumptions)
    if (
        total_cents <= 0
        or total_volume <= 0
        or not unit_count
        or common < 0
        or any(value < 0 for value in consumptions)
    ):
        raise ValueError(
            "A positive total and consistent metered volumes are required."
        )

    # Scale the denominator by the unit count to divide common volume without fractions.
    denominator = total_volume * unit_count
    weights = [volume * unit_count for volume in consumptions] + [common] * unit_count
    portions = [divmod(total_cents * weight, denominator) for weight in weights]
    shares = [cents for cents, _ in portions]
    remaining = total_cents - sum(shares)
    ranked = sorted(range(len(shares)), key=lambda index: -portions[index][1])
    for index in ranked[:remaining]:
        shares[index] += 1
    return list(zip(shares[:unit_count], shares[unit_count:], strict=True))
