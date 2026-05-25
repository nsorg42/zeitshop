from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from .detect import detect_encoding

DEFAULT_WIX_TEMPLATE_HEADER: tuple[str, ...] = (
    "handle",
    "fieldType",
    "name",
    "visible",
    "plainDescription",
    "categorySlugs",
    "primaryCategorySlug",
    "media",
    "mediaAltText",
    "ribbon",
    "brand",
    "price",
    "strikethroughPrice",
    "baseUnit",
    "baseUnitMeasurement",
    "totalUnits",
    "totalUnitsMeasurement",
    "cost",
    "inventory",
    "preOrderEnabled",
    "preOrderMessage",
    "preOrderLimit",
    "sku",
    "barcode",
    "weight",
    "productOptionName1",
    "productOptionType1",
    "productOptionChoices1",
    "productOptionName2",
    "productOptionType2",
    "productOptionChoices2",
    "productOptionName3",
    "productOptionType3",
    "productOptionChoices3",
    "productOptionName4",
    "productOptionType4",
    "productOptionChoices4",
    "productOptionName5",
    "productOptionType5",
    "productOptionChoices5",
    "productOptionName6",
    "productOptionType6",
    "productOptionChoices6",
    "modifierName1",
    "modifierType1",
    "modifierCharLimit1",
    "modifierMandatory1",
    "modifierDescription1",
    "modifierName2",
    "modifierType2",
    "modifierCharLimit2",
    "modifierMandatory2",
    "modifierDescription2",
    "modifierName3",
    "modifierType3",
    "modifierCharLimit3",
    "modifierMandatory3",
    "modifierDescription3",
    "modifierName4",
    "modifierType4",
    "modifierCharLimit4",
    "modifierMandatory4",
    "modifierDescription4",
    "modifierName5",
    "modifierType5",
    "modifierCharLimit5",
    "modifierMandatory5",
    "modifierDescription5",
    "modifierName6",
    "modifierType6",
    "modifierCharLimit6",
    "modifierMandatory6",
    "modifierDescription6",
    "modifierName7",
    "modifierType7",
    "modifierCharLimit7",
    "modifierMandatory7",
    "modifierDescription7",
    "modifierName8",
    "modifierType8",
    "modifierCharLimit8",
    "modifierMandatory8",
    "modifierDescription8",
    "modifierName9",
    "modifierType9",
    "modifierCharLimit9",
    "modifierMandatory9",
    "modifierDescription9",
    "modifierName10",
    "modifierType10",
    "modifierCharLimit10",
    "modifierMandatory10",
    "modifierDescription10",
)

REQUIRED_COLUMNS = {
    "handle",
    "fieldType",
    "name",
    "visible",
    "price",
    "inventory",
    "sku",
}


def _validate_header(header: list[str], source: str) -> list[str]:
    """Validate basic Wix template contract and return the same header."""
    if not header or not header[0]:
        raise ValueError(f"Template CSV has an invalid header row: {source}")

    missing = sorted(column for column in REQUIRED_COLUMNS if column not in header)
    if missing:
        raise ValueError(f"Template CSV is missing required columns: {', '.join(missing)}")

    return header


def default_template_header() -> list[str]:
    """Return a copy of the built-in Wix header."""
    return list(DEFAULT_WIX_TEMPLATE_HEADER)


def load_template_header(path: str | Path | None = None) -> list[str]:
    """Load Wix header from file, or use the baked-in default template.

    Parameters
    ----------
    path:
        Optional file path. If omitted, the built-in template header is used.
    """
    if path is None:
        return _validate_header(default_template_header(), source="built-in template")

    file_path = Path(path)
    raw_bytes = file_path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")

    reader = csv.reader(StringIO(text), delimiter=",")
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError(f"Template CSV is empty: {file_path}") from exc

    cleaned = [column.lstrip("\ufeff").strip() for column in header]
    return _validate_header(cleaned, source=str(file_path))
