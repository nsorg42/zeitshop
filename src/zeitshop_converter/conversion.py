from __future__ import annotations

from pathlib import Path

from .core import ConversionBatch, ConversionOptions, convert_records
from .io import load_template_header, read_diamond_csv


def convert_diamond_file(
    diamond_csv: str | Path,
    wix_template_csv: str | Path,
    options: ConversionOptions | None = None,
) -> ConversionBatch:
    records = read_diamond_csv(diamond_csv)
    header = load_template_header(wix_template_csv)
    return convert_records(records=records, template_header=header, options=options)
