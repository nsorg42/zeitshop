from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping, Sequence


def write_wix_csv(path: str | Path, header: Sequence[str], rows: Sequence[Mapping[str, str]]) -> int:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})

    return len(rows)
