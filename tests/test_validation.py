import pytest

from zeitshop_converter.core.models import Severity
from zeitshop_converter.core.validation import validate_wix_row


def _valid_row() -> dict[str, str]:
    return {
        "fieldType": "PRODUCT",
        "name": "Sample Product",
        "visible": "TRUE",
        "price": "10.00",
        "inventory": "2",
        "cost": "5.00",
        "sku": "SKU-1",
        "brand": "Brand",
    }


def test_validate_wix_row_accepts_valid_product_row() -> None:
    assert validate_wix_row(_valid_row(), source_row=2) == []


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"fieldType": "MEDIA"}, "fieldType", "fieldType must be PRODUCT for product rows."),
        ({"name": ""}, "name", "name is required."),
        ({"name": "x" * 81}, "name", "name exceeds 80 characters."),
        ({"visible": "yes"}, "visible", "visible must be TRUE or FALSE."),
        ({"price": ""}, "price", "price is required."),
        ({"price": "abc"}, "price", "price must be numeric."),
        ({"inventory": ""}, "inventory", "inventory is required."),
        ({"inventory": "1.5"}, "inventory", "inventory must be IN_STOCK, OUT_OF_STOCK, or an integer."),
        ({"cost": "1000000000.00"}, "cost", "cost must be numeric with <=9 whole digits and <=2 decimals."),
        ({"cost": "10.123"}, "cost", "cost must be numeric with <=9 whole digits and <=2 decimals."),
    ],
)
def test_validate_wix_row_reports_expected_errors(
    overrides: dict[str, str],
    field: str,
    message: str,
) -> None:
    row = _valid_row()
    row.update(overrides)

    issues = validate_wix_row(row, source_row=7)

    assert [(issue.field, issue.message, issue.source_row) for issue in issues] == [
        (field, message, 7)
    ]


def test_validate_wix_row_reports_length_warnings() -> None:
    row = _valid_row()
    row["sku"] = "s" * 41
    row["brand"] = "b" * 51

    issues = validate_wix_row(row, source_row=9)

    assert [(issue.field, issue.severity, issue.message) for issue in issues] == [
        ("sku", Severity.WARNING, "sku exceeds 40 characters."),
        ("brand", Severity.WARNING, "brand exceeds 50 characters."),
    ]


def test_validate_wix_row_accepts_boundary_cost_precision() -> None:
    row = _valid_row()
    row["cost"] = "999999999.00"

    assert validate_wix_row(row, source_row=11) == []
