from __future__ import annotations

from pathlib import Path
from typing import Callable

from .core import ConversionBatch, ConversionOptions, convert_records
from .io import (
    attach_media_rows,
    default_xlsx_image_mapping_path,
    load_template_header,
    read_diamond_file,
    write_image_mapping_csv,
)


def convert_diamond_file(
    diamond_csv: str | Path,
    wix_template_csv: str | Path | None = None,
    options: ConversionOptions | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> ConversionBatch:
    """Convert one DIAMOND CSV/XLSX file into validated Wix rows."""

    active_options = options or ConversionOptions()
    image_options = active_options.image_migration
    source_path = Path(diamond_csv).expanduser().resolve()
    should_extract_images = bool(
        image_options is not None
        and (image_options.enabled or image_options.export_embedded_images)
        and source_path.suffix.casefold() == ".xlsx"
    )
    image_export_dir = None
    if should_extract_images and image_options is not None:
        image_export_dir = image_options.export_directory.strip() or None

    if should_extract_images:
        records = read_diamond_file(
            diamond_csv,
            extract_embedded_images=True,
            image_export_dir=image_export_dir,
        )
    else:
        records = read_diamond_file(diamond_csv)

    if (
        should_extract_images
        and image_options is not None
        and image_options.export_embedded_images
    ):
        mapping_path = default_xlsx_image_mapping_path(
            source_path,
            output_dir=image_options.export_directory or None,
        )
        write_image_mapping_csv(mapping_path, records)

    header = load_template_header(wix_template_csv)
    batch = convert_records(records=records, template_header=header, options=active_options)

    if image_options is not None and image_options.enabled:
        attach_media_rows(
            batch=batch,
            options=image_options,
            source_file=diamond_csv,
            progress_callback=progress_callback,
        )

    return batch
