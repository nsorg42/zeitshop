#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path
import sys
from typing import Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zeitshop_converter.core.models import DiamondRecord
from zeitshop_converter.core.normalize import normalize_text
from zeitshop_converter.io import diamond_reader
from zeitshop_converter.io.detect import detect_encoding, sniff_dialect


def _record_identity(record: DiamondRecord) -> str:
    """Match converter merge identity: Artikel Nr, then Referenz, then row-id."""
    article_nr = normalize_text(record.data.get("Artikel Nr"))
    referenz = normalize_text(record.data.get("Referenz"))
    return article_nr or referenz or f"row-{record.source_row}"


def _summarize_records(records: Sequence[DiamondRecord]) -> tuple[int, int, dict[str, list[DiamondRecord]]]:
    """Return unique-product count, collapsed row count and duplicate buckets."""
    buckets: dict[str, list[DiamondRecord]] = defaultdict(list)
    for record in records:
        buckets[_record_identity(record)].append(record)

    collapsed = sum(len(rows) - 1 for rows in buckets.values() if len(rows) > 1)
    unique_products = len(records) - collapsed
    duplicates = {key: rows for key, rows in buckets.items() if len(rows) > 1}
    return unique_products, collapsed, duplicates


def _analyze_csv(path: Path) -> tuple[list[DiamondRecord], dict[str, int]]:
    """Run the same CSV parsing/filtering steps as read_diamond_csv with counters."""
    raw_bytes = path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")

    reader = csv.reader(StringIO(text), dialect=sniff_dialect(text[:4096]))
    try:
        raw_header = next(reader)
    except StopIteration:
        return [], {"header_row": 0, "rows_total": 0, "rows_data_area": 0}

    keep_indexes, final_header = diamond_reader._header_indexes(raw_header)
    stats = {
        "header_row": 1,
        "rows_total": 1,
        "rows_data_area": 0,
        "rows_empty": 0,
        "rows_without_identity": 0,
        "rows_header_like": 0,
        "rows_kept": 0,
    }

    records: list[DiamondRecord] = []
    for source_row, raw_row in enumerate(reader, start=2):
        stats["rows_total"] += 1
        stats["rows_data_area"] += 1

        if not any(diamond_reader._cell_to_text(cell) for cell in raw_row):
            stats["rows_empty"] += 1
            continue

        row_values = [raw_row[index] if index < len(raw_row) else "" for index in keep_indexes]
        row_map = dict(zip(final_header, row_values, strict=False))
        canonical = diamond_reader._canonicalize_row(row_map)

        if not diamond_reader._has_product_identity(canonical):
            stats["rows_without_identity"] += 1
            continue
        if diamond_reader._is_header_like_row(canonical):
            stats["rows_header_like"] += 1
            continue

        records.append(DiamondRecord(source_row=source_row, data=canonical))
        stats["rows_kept"] += 1

    return records, stats


def _analyze_xlsx(path: Path) -> tuple[list[DiamondRecord], dict[str, int]]:
    """Run the same XLSX parsing/filtering steps as read_diamond_xlsx with counters."""
    if diamond_reader.load_workbook is None:
        rows = diamond_reader._read_xlsx_rows_xml(path)
    else:
        workbook = diamond_reader.load_workbook(path, read_only=True, data_only=True)
        try:
            rows = list(workbook.active.iter_rows(values_only=True))
        finally:
            workbook.close()

    if not rows:
        return [], {"header_row": 0, "rows_total": 0, "rows_data_area": 0}

    header_row, keep_indexes, final_header = diamond_reader._find_header_row(rows)
    data_rows = rows[header_row:]
    stats = {
        "header_row": header_row,
        "rows_total": len(rows),
        "rows_data_area": len(data_rows),
        "rows_empty": 0,
        "rows_without_identity": 0,
        "rows_header_like": 0,
        "rows_kept": 0,
    }

    records: list[DiamondRecord] = []
    for source_row, raw_row in enumerate(data_rows, start=header_row + 1):
        if not any(diamond_reader._cell_to_text(cell) for cell in raw_row):
            stats["rows_empty"] += 1
            continue

        row_values = [raw_row[index] if index < len(raw_row) else "" for index in keep_indexes]
        row_map = dict(zip(final_header, row_values, strict=False))
        canonical = diamond_reader._canonicalize_row(row_map)

        if not diamond_reader._has_product_identity(canonical):
            stats["rows_without_identity"] += 1
            continue
        if diamond_reader._is_header_like_row(canonical):
            stats["rows_header_like"] += 1
            continue

        records.append(DiamondRecord(source_row=source_row, data=canonical))
        stats["rows_kept"] += 1

    return records, stats


def _print_duplicate_examples(duplicates: dict[str, list[DiamondRecord]], limit: int) -> None:
    """Print duplicate identities that were merged into single products."""
    if not duplicates:
        print("Doppelte Produkt-Identitäten: 0")
        return

    print(f"Doppelte Produkt-Identitäten: {len(duplicates)}")
    print(f"Beispiele (max {limit}):")

    sorted_items: Iterable[tuple[str, list[DiamondRecord]]] = sorted(
        duplicates.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    for index, (key, rows) in enumerate(sorted_items, start=1):
        if index > limit:
            break
        refs = sorted({normalize_text(row.data.get("Referenz")) for row in rows if normalize_text(row.data.get("Referenz"))})
        row_numbers = ", ".join(str(row.source_row) for row in rows)
        refs_text = ", ".join(refs) if refs else "-"
        print(f"  {index:>2}. Key={key} | Zeilen={row_numbers} | Referenz={refs_text}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Zählt Produkte in einem DIAMOND Export (CSV/XLSX) und zeigt, "
            "wie viele Zeilen beim Einlesen gefiltert oder beim Mergen zusammengeführt werden."
        )
    )
    parser.add_argument("file", type=Path, help="Pfad zur DIAMOND Datei (.csv oder .xlsx)")
    parser.add_argument(
        "--duplicates",
        type=int,
        default=10,
        help="Wie viele zusammengeführte Duplikat-Beispiele angezeigt werden sollen (Default: 10).",
    )
    args = parser.parse_args()

    file_path = args.file.expanduser().resolve()
    if not file_path.exists():
        print(f"Datei nicht gefunden: {file_path}")
        return 2

    suffix = file_path.suffix.casefold()
    if suffix == ".xlsx":
        records, stats = _analyze_xlsx(file_path)
    elif suffix == ".csv":
        records, stats = _analyze_csv(file_path)
    else:
        print(f"Nicht unterstützt: {file_path.suffix} (nur .csv/.xlsx)")
        return 2

    unique_products, collapsed_rows, duplicates = _summarize_records(records)

    print(f"Datei: {file_path}")
    print(f"Gefundene Header-Zeile: {stats.get('header_row', 0)}")
    print(f"Zeilen total (Sheet/Datei): {stats.get('rows_total', 0)}")
    print(f"Zeilen im Datenbereich: {stats.get('rows_data_area', 0)}")
    print(f"Leere Zeilen übersprungen: {stats.get('rows_empty', 0)}")
    print(f"Zeilen ohne Produktidentität übersprungen: {stats.get('rows_without_identity', 0)}")
    print(f"Wiederholte Header-Zeilen übersprungen: {stats.get('rows_header_like', 0)}")
    print(f"Produktzeilen nach Reader-Filter: {stats.get('rows_kept', 0)}")
    print(f"Beim Merge zusammengeführt: {collapsed_rows}")
    print(f"Finale Produktanzahl (wie Konverter): {unique_products}")
    print()
    _print_duplicate_examples(duplicates, limit=max(args.duplicates, 0))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
