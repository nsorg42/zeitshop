from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
import re
from typing import Mapping, Sequence

from ..core.models import DiamondRecord
from ..core.normalize import normalize_text
from .detect import detect_encoding, sniff_dialect


CANONICAL_COLUMNS = [
    "Bild",
    "Filiale",
    "Kategorie",
    "Warengruppe",
    "Marke",
    "Produktlinie",
    "Artikel Nr",
    "Kurzbeschreibung",
    "Referenz",
    "Menge",
    "Einstand",
    "Verkauf",
]


ALIASES: dict[str, str] = {
    "bild": "Bild",
    "filiale": "Filiale",
    "kategorie": "Kategorie",
    "warengruppe": "Warengruppe",
    "marke": "Marke",
    "produktlinie": "Produktlinie",
    "artikel nr": "Artikel Nr",
    "artikelnr": "Artikel Nr",
    "kurzbeschreibung": "Kurzbeschreibung",
    "referenz": "Referenz",
    "menge": "Menge",
    "einstand": "Einstand",
    "verkauf": "Verkauf",
}


def _canonical_header(raw_header: str) -> str:
    """Normalize source header and map aliases to canonical names."""
    cleaned = normalize_text(raw_header).lstrip("\ufeff")
    key = cleaned.casefold()
    return ALIASES.get(key, cleaned)


def _cell_to_text(value: object) -> str:
    """Convert CSV cell values to normalized text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return normalize_text(str(value))


def _header_indexes(raw_header: Sequence[object]) -> tuple[list[int], list[str]]:
    cleaned_header = [_canonical_header(_cell_to_text(value)) for value in raw_header]
    keep_indexes = [index for index, header in enumerate(cleaned_header) if header]
    final_header = [cleaned_header[index] for index in keep_indexes]
    return keep_indexes, final_header


def _canonicalize_row(row: Mapping[str, object]) -> dict[str, str]:
    """Project arbitrary row dict into the fixed canonical DIAMOND schema."""
    canonical = {column: "" for column in CANONICAL_COLUMNS}
    for key, value in row.items():
        canonical_key = _canonical_header(key)
        if canonical_key in canonical:
            canonical[canonical_key] = _cell_to_text(value)
    return canonical


def _has_product_identity(canonical_row: Mapping[str, str]) -> bool:
    return bool(
        canonical_row.get("Artikel Nr")
        or canonical_row.get("Referenz")
        or canonical_row.get("Kurzbeschreibung")
    )


def _tokenize_header_candidate(value: str) -> str:
    """Normalize a text token for robust header-like row comparisons."""
    return re.sub(r"[^0-9a-z]+", "", normalize_text(value).casefold())


_HEADER_TOKENS = {
    column: _tokenize_header_candidate(column) for column in CANONICAL_COLUMNS
}
_IDENTITY_COLUMNS = ("Artikel Nr", "Referenz", "Kurzbeschreibung")


def _is_header_like_row(canonical_row: Mapping[str, str]) -> bool:
    """Detect repeated in-body header rows from paginated DIAMOND exports."""
    matches = 0
    identity_matches = 0

    for column, expected_token in _HEADER_TOKENS.items():
        value_token = _tokenize_header_candidate(canonical_row.get(column, ""))
        if not value_token or value_token != expected_token:
            continue
        matches += 1
        if column in _IDENTITY_COLUMNS:
            identity_matches += 1

    return identity_matches >= 1 and matches >= 3


def read_diamond_csv(path: str | Path) -> list[DiamondRecord]:
    """Read a DIAMOND CSV file into canonical `DiamondRecord` objects."""

    file_path = Path(path)
    raw_bytes = file_path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")

    sample = text[:4096]
    dialect = sniff_dialect(sample)

    stream = StringIO(text)
    reader = csv.reader(stream, dialect=dialect)

    try:
        raw_header = next(reader)
    except StopIteration:
        return []

    keep_indexes, final_header = _header_indexes(raw_header)

    records: list[DiamondRecord] = []
    for source_row, raw_row in enumerate(reader, start=2):
        if not any(_cell_to_text(cell) for cell in raw_row):
            continue

        row_values = [raw_row[index] if index < len(raw_row) else "" for index in keep_indexes]
        row_map = dict(zip(final_header, row_values, strict=False))
        canonical = _canonicalize_row(row_map)

        # Ignore footer rows that carry totals but no product identity.
        if not _has_product_identity(canonical):
            continue
        if _is_header_like_row(canonical):
            continue

        records.append(DiamondRecord(source_row=source_row, data=canonical))

    return records


def read_diamond_file(path: str | Path) -> list[DiamondRecord]:
    """Read DIAMOND exports from CSV."""
    file_path = Path(path)
    suffix = file_path.suffix.casefold()
    if suffix == ".csv":
        return read_diamond_csv(file_path)

    raise ValueError(
        f"Unsupported DIAMOND format '{file_path.suffix}'. "
        "Please provide a .csv file."
    )
