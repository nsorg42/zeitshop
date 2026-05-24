from __future__ import annotations

from pathlib import Path
from typing import Callable

from .core import ConversionBatch, ConversionOptions, convert_records
from .io import (
    attach_archive_media_rows,
    load_template_header,
    read_diamond_file,
)


def convert_diamond_file(
    diamond_csv: str | Path,
    wix_template_csv: str | Path | None = None,
    options: ConversionOptions | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> ConversionBatch:
    """Convert one DIAMOND CSV file into validated Wix rows."""

    active_options = options or ConversionOptions()
    image_options = active_options.image_archive
    records = read_diamond_file(Path(diamond_csv).expanduser())
    header = load_template_header(wix_template_csv)
    batch = convert_records(records=records, template_header=header, options=active_options)

    if image_options is not None and image_options.enabled:
        attach_archive_media_rows(
            batch=batch,
            options=image_options,
            progress_callback=progress_callback,
        )

    return batch
