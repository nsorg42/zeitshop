#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from io import StringIO
from pathlib import Path


DESCRIPTION_COLUMN = "plainDescription"
OLD_TEXT = (
    "Verfügbar in der Bijouterie Am Bogen in Bremgarten AG "
    "und in der Bijouterie Droz in Zofingen AG"
)
NEW_TEXT = (
    "Verfügbar in der Bijouterie am Bogen in Bremgarten AG "
    "und in der Bijouterie Droz in Zofingen AG"
)


def detect_encoding(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    return "latin1"


def sniff_dialect(text: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        return csv.excel


def normalize_header(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]], csv.Dialect, str]:
    raw_bytes = path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")
    dialect = sniff_dialect(text)
    reader = csv.DictReader(StringIO(text), dialect=dialect)
    header = [normalize_header(field) for field in (reader.fieldnames or [])]
    if not header:
        raise ValueError(f"CSV has no header row: {path}")

    reader.fieldnames = header
    return header, [dict(row) for row in reader], dialect, encoding


def write_csv(
    path: Path,
    header: list[str],
    rows: list[dict[str, str]],
    dialect: csv.Dialect,
    encoding: str,
) -> None:
    output_encoding = "utf-8-sig" if encoding == "utf-8-sig" else encoding
    with path.open("w", encoding=output_encoding, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=header, dialect=dialect, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_am_bogen_fixed{input_path.suffix}")


def update_descriptions(input_path: Path, output_path: Path) -> tuple[int, int]:
    header, rows, dialect, encoding = read_csv(input_path)
    if DESCRIPTION_COLUMN not in header:
        raise ValueError(f"CSV is missing required column: {DESCRIPTION_COLUMN}")

    changed_rows = 0
    replacements = 0
    for row in rows:
        description = row.get(DESCRIPTION_COLUMN) or ""
        count = description.count(OLD_TEXT)
        if count == 0:
            continue
        row[DESCRIPTION_COLUMN] = description.replace(OLD_TEXT, NEW_TEXT)
        changed_rows += 1
        replacements += count

    write_csv(output_path, header, rows, dialect, encoding)
    return changed_rows, replacements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decapitalize 'Am Bogen' in the combined-store availability phrase."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("current inventory.csv"),
        help="Path to the Wix inventory CSV. Defaults to 'current inventory.csv' next to this script.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path for the updated CSV. Defaults to '<input>_am_bogen_fixed.csv'.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the input CSV instead of writing a new file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = args.csv_path if args.in_place else args.output or default_output_path(args.csv_path)
    changed_rows, replacements = update_descriptions(args.csv_path, output_path)

    print(f"Rows changed: {changed_rows}")
    print(f"Phrase replacements: {replacements}")
    print(f"Updated CSV written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
