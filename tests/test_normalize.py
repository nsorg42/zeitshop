from decimal import Decimal

import pytest

from zeitshop_converter.core.normalize import (
    format_decimal,
    make_handle,
    normalize_inventory,
    normalize_text,
    parse_decimal,
    parse_quantity,
)


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


def test_normalize_text_and_format_decimal_handle_empty_values() -> None:
    assert normalize_text("  a   b  ") == "a b"
    assert normalize_text(None) == ""
    assert parse_decimal("") is None
    assert format_decimal(Decimal("10"), places=2) == "10.00"


def test_normalize_inventory_numeric_mode() -> None:
    assert normalize_inventory("4", numeric_inventory=True) == "4"
    assert normalize_inventory("", numeric_inventory=True) == "0"
    assert normalize_inventory("-2", numeric_inventory=True) == "0"


def test_normalize_inventory_stock_mode() -> None:
    assert normalize_inventory("2", numeric_inventory=False) == "IN_STOCK"
    assert normalize_inventory("0", numeric_inventory=False) == "OUT_OF_STOCK"
    assert normalize_inventory("-1", numeric_inventory=False) == "OUT_OF_STOCK"


@pytest.mark.parametrize("raw", ["1.9", "1,9", "0.5"])
def test_parse_quantity_rejects_fractional_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_quantity(raw)


def test_make_handle_strips_unsafe_characters() -> None:
    assert make_handle("AB 12/34", prefix="ds-") == "ds-ab-1234"
    assert make_handle("  Fancy  Name  ", prefix="") == "fancy-name"
