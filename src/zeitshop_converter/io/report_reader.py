from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from ..core.normalize import normalize_text
from .detect import detect_encoding, sniff_dialect


@dataclass(frozen=True)
class ReportDescriptionRecord:
    """One description block extracted from a report.csv export."""

    source_row: int
    artikel_nr: str
    referenz: str
    beschreibung: str


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return normalize_text(row[index])


def _parse_identity(text: str) -> tuple[str, str] | None:
    if "|" not in text:
        return None
    parts = [normalize_text(part) for part in text.split("|", 1)]
    if len(parts) != 2:
        return None
    artikel_nr, referenz = parts
    if ":" in artikel_nr or ":" in referenz:
        return None
    if not any(character.isdigit() for character in artikel_nr):
        return None
    if not artikel_nr and not referenz:
        return None
    return artikel_nr, referenz


def read_report_description_csv(path: str | Path) -> list[ReportDescriptionRecord]:
    """Read a report.csv-style export into product description records."""

    file_path = Path(path)
    raw_bytes = file_path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")
    reader = csv.reader(StringIO(text), dialect=sniff_dialect(text[:4096]))

    records: list[ReportDescriptionRecord] = []
    current_identity: tuple[int, str, str] | None = None
    description_lines: list[str] = []

    def flush() -> None:
        nonlocal current_identity, description_lines
        if current_identity is None:
            description_lines = []
            return

        source_row, artikel_nr, referenz = current_identity
        beschreibung = "\n".join(line for line in description_lines if line)
        if beschreibung:
            records.append(
                ReportDescriptionRecord(
                    source_row=source_row,
                    artikel_nr=artikel_nr,
                    referenz=referenz,
                    beschreibung=beschreibung,
                )
            )
        current_identity = None
        description_lines = []

    for source_row, raw_row in enumerate(reader, start=1):
        description_cell = _cell(raw_row, 2)
        price = _cell(raw_row, 3)

        if not any(normalize_text(value) for value in raw_row):
            continue

        if description_cell and price:
            flush()
            continue

        identity = _parse_identity(description_cell)
        if identity is not None:
            flush()
            artikel_nr, referenz = identity
            current_identity = (source_row, artikel_nr, referenz)
            continue

        if description_cell and current_identity is not None:
            description_lines.append(description_cell)

    flush()
    return records
