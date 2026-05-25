from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Mapping

from .models import Severity, ValidationIssue
from .normalize import normalize_text


_ALLOWED_FIELD_TYPES = {"PRODUCT"}
_ALLOWED_VISIBLE = {"TRUE", "FALSE"}
_ALLOWED_INVENTORY = {"IN_STOCK", "OUT_OF_STOCK"}
_INTEGER_RE = re.compile(r"^-?\d+$")


def _parse_decimal(text: str) -> Decimal | None:
    """Safe decimal parser for validator checks (returns None on invalid)."""
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _validate_cost_precision(text: str) -> bool:
    """Check Wix-style cost precision rules for whole and fractional digits."""
    value = _parse_decimal(text)
    if value is None:
        return False

    normalized = format(value.normalize(), "f") if value != 0 else "0"
    if "." in normalized:
        whole, fraction = normalized.split(".", 1)
    else:
        whole, fraction = normalized, ""

    whole = whole.lstrip("-")
    return len(whole) <= 9 and len(fraction.rstrip("0")) <= 2


def validate_wix_row(row: Mapping[str, str], source_row: int) -> list[ValidationIssue]:
    """Validate one mapped Wix row and return all detected issues."""

    issues: list[ValidationIssue] = []

    field_type = normalize_text(row.get("fieldType"))
    if field_type not in _ALLOWED_FIELD_TYPES:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="fieldType",
                severity=Severity.ERROR,
                message="fieldType must be PRODUCT for product rows.",
            )
        )

    name = normalize_text(row.get("name"))
    if not name:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="name",
                severity=Severity.ERROR,
                message="name is required.",
            )
        )
    elif len(name) > 80:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="name",
                severity=Severity.ERROR,
                message="name exceeds 80 characters.",
            )
        )

    visible = normalize_text(row.get("visible"))
    if visible not in _ALLOWED_VISIBLE:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="visible",
                severity=Severity.ERROR,
                message="visible must be TRUE or FALSE.",
            )
        )

    price = normalize_text(row.get("price"))
    if not price:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="price",
                severity=Severity.ERROR,
                message="price is required.",
            )
        )
    elif _parse_decimal(price) is None:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="price",
                severity=Severity.ERROR,
                message="price must be numeric.",
            )
        )

    inventory = normalize_text(row.get("inventory"))
    if not inventory:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="inventory",
                severity=Severity.ERROR,
                message="inventory is required.",
            )
        )
    elif inventory not in _ALLOWED_INVENTORY and not _INTEGER_RE.match(inventory):
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="inventory",
                severity=Severity.ERROR,
                message="inventory must be IN_STOCK, OUT_OF_STOCK, or an integer.",
            )
        )

    cost = normalize_text(row.get("cost"))
    if cost and not _validate_cost_precision(cost):
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="cost",
                severity=Severity.ERROR,
                message="cost must be numeric with <=9 whole digits and <=2 decimals.",
            )
        )

    sku = normalize_text(row.get("sku"))
    if not sku:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="sku",
                severity=Severity.ERROR,
                message="sku is required.",
            )
        )
    elif len(sku) > 40:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="sku",
                severity=Severity.WARNING,
                message="sku exceeds 40 characters.",
            )
        )

    brand = normalize_text(row.get("brand"))
    if len(brand) > 50:
        issues.append(
            ValidationIssue(
                source_row=source_row,
                field="brand",
                severity=Severity.WARNING,
                message="brand exceeds 50 characters.",
            )
        )

    return issues
