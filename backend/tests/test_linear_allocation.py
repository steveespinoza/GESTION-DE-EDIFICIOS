import pytest

from app.billing.allocation import split_linear


@pytest.mark.parametrize(
    ("total", "count", "expected"),
    [
        (10000, 3, [3334, 3333, 3333]),
        (8, 3, [3, 3, 2]),
        (9, 3, [3, 3, 3]),
        (1, 3, [1, 0, 0]),
        (999999999999, 1, [999999999999]),
    ],
)
def test_linear_allocation_distributes_cents_without_losing_any(total, count, expected):
    amounts = split_linear(total, count)
    assert amounts == expected
    assert sum(amounts) == total


@pytest.mark.parametrize(("total", "count"), [(0, 2), (20, 0)])
def test_linear_allocation_requires_a_positive_total_and_units(total, count):
    with pytest.raises(ValueError, match="positive total"):
        split_linear(total, count)
