from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


_SPACE_RE = re.compile(r"\s+")
_HANDLE_RE = re.compile(r"[^a-z0-9-]+")
_GERMAN_SLUG_REPLACEMENTS = str.maketrans({
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "ß": "ss",
})


def normalize_text(value: str | None) -> str:
    """Trim a string and collapse repeated whitespace to single spaces."""
    if value is None:
        return ""
    text = _SPACE_RE.sub(" ", value.strip())
    return text


def parse_decimal(value: str | None) -> Decimal | None:
    """Parse human-entered decimal values, including Swiss separators.

    Returns `None` for empty input and raises `ValueError` for invalid numbers.
    """
    text = normalize_text(value)
    if not text:
        return None

    # Remove common thousands separators seen in CH exports.
    text = text.replace("’", "").replace("'", "").replace(" ", "")

    # If both comma and dot exist, the last one is treated as decimal mark.
    if "," in text and "." in text:
        last_comma = text.rfind(",")
        last_dot = text.rfind(".")
        decimal_sep = "," if last_comma > last_dot else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "")
        if decimal_sep == ",":
            text = text.replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc


def format_decimal(value: Decimal | None, places: int = 2) -> str:
    """Format Decimal as fixed-point string with given decimal places."""
    if value is None:
        return ""
    quant = Decimal("1").scaleb(-places)
    return format(value.quantize(quant), f"f")


def parse_quantity(value: str | None) -> int | None:
    """Parse quantity input and return integer quantity when possible."""
    text = normalize_text(value)
    if not text:
        return None

    text = text.replace("’", "").replace("'", "").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "")
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        quantity = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid quantity value: {value!r}") from exc

    if quantity != quantity.to_integral_value():
        raise ValueError(f"invalid quantity value: {value!r}")

    return int(quantity)


def normalize_inventory(value: str | None, numeric_inventory: bool = True) -> str:
    """Convert raw quantity into Wix inventory value.

    numeric_inventory=True returns string quantities like "3".
    numeric_inventory=False returns status enums like IN_STOCK/OUT_OF_STOCK.
    """
    qty = parse_quantity(value)
    if qty is None:
        return "OUT_OF_STOCK" if not numeric_inventory else "0"
    if numeric_inventory:
        return str(max(qty, 0))
    return "IN_STOCK" if qty > 0 else "OUT_OF_STOCK"


def make_handle(raw: str | None, prefix: str = "ds-") -> str:
    """Create a URL-safe handle string from free-form text."""
    body = normalize_text(raw).lower()
    body = body.translate(_GERMAN_SLUG_REPLACEMENTS)
    body = body.replace(" ", "-")
    body = _HANDLE_RE.sub("", body)
    body = re.sub(r"-+", "-", body).strip("-")
    if not body:
        return prefix.rstrip("-")
    if prefix:
        return f"{prefix}{body}"
    return body
