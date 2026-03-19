from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Mapping

from ..core.models import DiamondRecord
from ..core.normalize import normalize_text
from .detect import detect_encoding, sniff_dialect


CANONICAL_COLUMNS = [
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
    cleaned = normalize_text(raw_header).lstrip("\ufeff")
    key = cleaned.casefold()
    return ALIASES.get(key, cleaned)


def _canonicalize_row(row: Mapping[str, str]) -> dict[str, str]:
    canonical = {column: "" for column in CANONICAL_COLUMNS}
    for key, value in row.items():
        canonical_key = _canonical_header(key)
        if canonical_key in canonical:
            canonical[canonical_key] = normalize_text(value)
    return canonical


def read_diamond_csv(path: str | Path) -> list[DiamondRecord]:
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

    cleaned_header = [_canonical_header(value) for value in raw_header]
    keep_indexes = [
        index
        for index, header in enumerate(cleaned_header)
        if header and header.casefold() != "bild"
    ]

    final_header = [cleaned_header[index] for index in keep_indexes]

    records: list[DiamondRecord] = []
    for source_row, raw_row in enumerate(reader, start=2):
        if not any(normalize_text(cell) for cell in raw_row):
            continue

        row_values = [raw_row[index] if index < len(raw_row) else "" for index in keep_indexes]
        row_map = dict(zip(final_header, row_values, strict=False))
        canonical = _canonicalize_row(row_map)

        # Ignore footer/summary rows that carry totals but no product identity.
        if not (
            canonical.get("Artikel Nr")
            or canonical.get("Referenz")
            or canonical.get("Kurzbeschreibung")
        ):
            continue

        records.append(DiamondRecord(source_row=source_row, data=canonical))

    return records
