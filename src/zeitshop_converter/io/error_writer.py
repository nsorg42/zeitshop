from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

from ..core.models import WixRowResult


def write_error_csv(path: str | Path, error_rows: Sequence[WixRowResult]) -> int:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    source_fields: list[str] = []
    seen: set[str] = set()
    for result in error_rows:
        for key in result.source.keys():
            if key not in seen:
                seen.add(key)
                source_fields.append(key)

    header = ["source_row", *source_fields, "error_codes", "error_messages"]

    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for result in error_rows:
            codes = [f"{issue.severity.value}:{issue.field}" for issue in result.issues]
            messages = [issue.message for issue in result.issues]
            row = {
                "source_row": str(result.source_row),
                "error_codes": " | ".join(codes),
                "error_messages": " | ".join(messages),
            }
            for field in source_fields:
                row[field] = result.source.get(field, "")
            writer.writerow(row)

    return len(error_rows)
