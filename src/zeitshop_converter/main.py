from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .conversion import convert_diamond_file
from .core import ConversionOptions, ImageMigrationOptions
from .gui import run_gui
from .io import (
    default_xlsx_image_mapping_path,
    read_diamond_xlsx,
    resolve_xlsx_image_export_dir,
    write_error_csv,
    write_image_mapping_csv,
    write_wix_csv,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser used by both script and module entrypoints."""

    parser = argparse.ArgumentParser(prog="zeitshop-converter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="start the desktop GUI")

    convert = sub.add_parser("convert", help="convert a DIAMOND CSV/XLSX into Wix import CSV")
    convert.add_argument("--diamond", required=True, help="path to DIAMOND CSV/XLSX")
    convert.add_argument(
        "--template",
        help="optional path to a Wix template CSV (defaults to the built-in header)",
    )
    convert.add_argument("--output", required=True, help="path for generated Wix CSV")
    convert.add_argument(
        "--issues-output",
        help="optional path for issue report CSV",
    )
    convert.add_argument(
        "--error-output",
        dest="issues_output",
        help=argparse.SUPPRESS,
    )
    convert.add_argument("--default-visible", action="store_true", help="set visible=TRUE by default")
    convert.add_argument(
        "--inventory-mode",
        choices=("numeric", "stock"),
        default="numeric",
        help="numeric => write quantities, stock => IN_STOCK/OUT_OF_STOCK",
    )
    convert.add_argument("--handle-prefix", default="ds-", help="prefix used for generated handles")
    convert.add_argument(
        "--images-dir",
        help="optional directory to scan recursively for product images",
    )
    convert.add_argument(
        "--export-embedded-images",
        action="store_true",
        help="extract embedded XLSX images into a folder and write a row mapping CSV",
    )
    convert.add_argument(
        "--image-export-dir",
        help="directory where embedded XLSX images and the mapping CSV should be written",
    )
    convert.add_argument(
        "--wix-site-id",
        help="optional Wix site ID used for automatic local image uploads",
    )
    convert.add_argument(
        "--wix-api-key",
        help="optional Wix API key used for automatic local image uploads",
    )
    convert.add_argument(
        "--wix-image-path",
        default="/zeitshop",
        help="target Media Manager folder path for uploaded images",
    )

    export_images = sub.add_parser(
        "export-images",
        help="extract embedded images from a DIAMOND XLSX and write a row mapping CSV",
    )
    export_images.add_argument("--diamond", required=True, help="path to DIAMOND XLSX")
    export_images.add_argument(
        "--output-dir",
        help="directory where extracted images should be written",
    )
    export_images.add_argument(
        "--mapping-output",
        help="optional CSV path for source-row to image mapping",
    )

    return parser


def _run_convert(args: argparse.Namespace) -> int:
    """Execute CLI conversion mode and write output files."""

    wix_site_id = args.wix_site_id or os.environ.get("ZEITSHOP_WIX_SITE_ID", "")
    wix_api_key = args.wix_api_key or os.environ.get("ZEITSHOP_WIX_API_KEY", "")
    image_export_dir = args.image_export_dir or ""
    options = ConversionOptions(
        default_visible=args.default_visible,
        numeric_inventory=args.inventory_mode == "numeric",
        handle_prefix=args.handle_prefix,
        image_migration=ImageMigrationOptions(
            enabled=bool(args.images_dir or wix_site_id or wix_api_key),
            image_directory=args.images_dir or "",
            export_embedded_images=args.export_embedded_images,
            export_directory=image_export_dir,
            wix_site_id=wix_site_id,
            wix_api_key=wix_api_key,
            wix_file_path=args.wix_image_path,
        ),
    )

    batch = convert_diamond_file(
        diamond_csv=args.diamond,
        wix_template_csv=args.template,
        options=options,
        progress_callback=print if options.image_migration and options.image_migration.enabled else None,
    )

    output_rows = write_wix_csv(args.output, batch.header, batch.valid_rows)

    if args.issues_output:
        write_error_csv(args.issues_output, batch.issue_rows)

    print(f"Converted rows: {len(batch.results)}")
    print(f"Valid products: {len(batch.valid_product_rows)}")
    print(f"Written CSV rows: {output_rows}")
    print(f"Rows with errors: {len(batch.error_rows)}")
    print(f"Rows with warnings: {batch.warning_count}")

    return 0


def _run_export_images(args: argparse.Namespace) -> int:
    """Extract embedded XLSX images and export a mapping CSV for inspection."""

    diamond_path = Path(args.diamond)
    if diamond_path.suffix.casefold() != ".xlsx":
        raise ValueError("The export-images command currently supports only .xlsx files.")

    output_dir = resolve_xlsx_image_export_dir(
        diamond_path,
        output_dir=args.output_dir,
    )
    records = read_diamond_xlsx(
        diamond_path,
        extract_embedded_images=True,
        image_export_dir=output_dir,
    )

    mapping_output = (
        Path(args.mapping_output).expanduser()
        if args.mapping_output
        else default_xlsx_image_mapping_path(diamond_path, output_dir=output_dir)
    )
    mapped_rows = write_image_mapping_csv(mapping_output, records)

    print(f"Extracted image directory: {output_dir}")
    print(f"Rows with images: {mapped_rows}")
    print(f"Image mapping CSV: {mapping_output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Program entrypoint used by `python -m` and console scripts."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "gui"):
        run_gui()
        return 0

    if args.command == "convert":
        return _run_convert(args)

    if args.command == "export-images":
        return _run_export_images(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
