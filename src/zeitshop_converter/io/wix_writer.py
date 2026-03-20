from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping, Sequence


def write_wix_csv(path: str | Path, header: Sequence[str], rows: Sequence[Mapping[str, str]]) -> int:
    """Write Wix import CSV with exact header order.

    csv.DictWriter from Python's stdlib handles quoting and comma escaping.

    Parameters
    ----------
    path:
        Output file location.
    header:
        Ordered column names expected by Wix import.
    rows:
        Row dictionaries to serialize.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})

    return len(rows)
