from decimal import Decimal

import pytest

from zeitshop_converter.core.normalize import make_handle, normalize_inventory, parse_decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1'775.00", Decimal("1775.00")),
        ("1’775.00", Decimal("1775.00")),
        ("3 550.00", Decimal("3550.00")),
        ("40,85", Decimal("40.85")),
    ],
)
def test_parse_decimal_accepts_swiss_formats(raw: str, expected: Decimal) -> None:
    assert parse_decimal(raw) == expected


def test_parse_decimal_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        parse_decimal("abc")


def test_normalize_inventory_numeric_mode() -> None:
    assert normalize_inventory("4", numeric_inventory=True) == "4"
    assert normalize_inventory("", numeric_inventory=True) == "0"


def test_normalize_inventory_stock_mode() -> None:
    assert normalize_inventory("2", numeric_inventory=False) == "IN_STOCK"
    assert normalize_inventory("0", numeric_inventory=False) == "OUT_OF_STOCK"


def test_make_handle_strips_unsafe_characters() -> None:
    assert make_handle("AB 12/34", prefix="ds-") == "ds-ab-1234"
