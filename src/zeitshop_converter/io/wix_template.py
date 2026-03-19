from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from .detect import detect_encoding

_REQUIRED_COLUMNS = {
    "handle",
    "fieldType",
    "name",
    "visible",
    "price",
    "inventory",
    "sku",
}


def load_template_header(path: str | Path) -> list[str]:
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
    if not cleaned or not cleaned[0]:
        raise ValueError(f"Template CSV has an invalid header row: {file_path}")

    missing = sorted(column for column in _REQUIRED_COLUMNS if column not in cleaned)
    if missing:
        raise ValueError(
            f"Template CSV is missing required columns: {', '.join(missing)}"
        )

    return cleaned
