from __future__ import annotations

from pathlib import Path

from .core import ConversionBatch, ConversionOptions, convert_records
from .io import (
    load_template_header,
    read_diamond_file,
)


def convert_diamond_file(
    diamond_csv: str | Path,
    wix_template_csv: str | Path | None = None,
    options: ConversionOptions | None = None,
) -> ConversionBatch:
    """Convert one DIAMOND CSV file into validated Wix rows."""

    active_options = options or ConversionOptions()
    records = read_diamond_file(Path(diamond_csv).expanduser())
    header = load_template_header(wix_template_csv)
    return convert_records(records=records, template_header=header, options=active_options)
