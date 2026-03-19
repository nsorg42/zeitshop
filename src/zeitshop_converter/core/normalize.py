from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


_SPACE_RE = re.compile(r"\s+")
_HANDLE_RE = re.compile(r"[^a-z0-9-]+")


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    text = _SPACE_RE.sub(" ", value.strip())
    return text


def parse_decimal(value: str | None) -> Decimal | None:
    text = normalize_text(value)
    if not text:
        return None

    text = text.replace("’", "").replace("'", "").replace(" ", "")

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
    if value is None:
        return ""
    quant = Decimal("1").scaleb(-places)
    return format(value.quantize(quant), f"f")


def parse_quantity(value: str | None) -> int | None:
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
        return int(Decimal(text))
    except InvalidOperation as exc:
        raise ValueError(f"invalid quantity value: {value!r}") from exc


def normalize_inventory(value: str | None, numeric_inventory: bool = True) -> str:
    qty = parse_quantity(value)
    if qty is None:
        return "OUT_OF_STOCK" if not numeric_inventory else "0"
    if numeric_inventory:
        return str(max(qty, 0))
    return "IN_STOCK" if qty > 0 else "OUT_OF_STOCK"


def make_handle(raw: str | None, prefix: str = "ds-") -> str:
    body = normalize_text(raw).lower()
    body = body.replace(" ", "-")
    body = _HANDLE_RE.sub("", body)
    body = re.sub(r"-+", "-", body).strip("-")
    if not body:
        return prefix.rstrip("-")
    if prefix:
        return f"{prefix}{body}"
    return body
