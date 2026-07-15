from __future__ import annotations

import argparse
import sys

from .conversion import convert_diamond_file
from .core import ConversionOptions
from .gui import run_gui
from .inventory_update import build_inventory_update_batch
from .io import write_error_csv, write_wix_csv


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser used by both script and module entrypoints."""

    parser = argparse.ArgumentParser(prog="zeitshop-converter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="start the desktop GUI")

    convert = sub.add_parser(
        "convert", help="convert a DIAMOND CSV into Wix import CSV"
    )
    convert.add_argument("--diamond", required=True, help="path to DIAMOND CSV")
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
    convert.add_argument(
        "--default-visible", action="store_true", help="set visible=TRUE by default"
    )
    convert.add_argument(
        "--inventory-mode",
        choices=("numeric", "stock"),
        default="numeric",
        help="numeric => write quantities, stock => IN_STOCK/OUT_OF_STOCK",
    )
    convert.add_argument(
        "--handle-prefix", default="ds-", help="prefix used for generated handles"
    )

    update = sub.add_parser(
        "update",
        aliases=["update-inventory"],
        help="update a Wix export CSV with current DIAMOND inventory",
    )
    update.add_argument(
        "--wix-export",
        required=True,
        help="path to the Wix product export CSV to update",
    )
    update.add_argument(
        "--diamond",
        required=True,
        help="path to current DIAMOND inventory CSV",
    )
    update.add_argument("--output", required=True, help="path for updated Wix CSV")

    return parser


def _run_convert(args: argparse.Namespace) -> int:
    """Execute CLI conversion mode and write output files."""

    options = ConversionOptions(
        default_visible=args.default_visible,
        numeric_inventory=args.inventory_mode == "numeric",
        handle_prefix=args.handle_prefix,
    )

    batch = convert_diamond_file(
        diamond_csv=args.diamond,
        wix_template_csv=args.template,
        options=options,
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


def _run_update(args: argparse.Namespace) -> int:
    """Execute CLI inventory-update mode and write the updated Wix export."""

    batch = build_inventory_update_batch(
        wix_export_csv=args.wix_export,
        diamond_csv=args.diamond,
    )
    if batch.has_blocking_errors:
        print("Inventory update blocked by safety errors.")
        print(f"Rows with errors: {batch.error_count}")
        print(f"Rows with warnings: {batch.warning_count}")
        return 1

    output_rows = write_wix_csv(args.output, batch.header, batch.rows)

    print(f"Wix rows written: {output_rows}")
    print(f"Product rows checked: {len(batch.results)}")
    print(f"Matched products: {batch.matched_count}")
    print(f"Products set to zero: {batch.set_to_zero_count}")
    print(f"New products: {batch.new_product_count}")
    print(f"Changed products: {batch.changed_count}")
    print(f"Unmatched DIAMOND rows: {batch.unmatched_diamond_count}")

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

    if args.command in ("update", "update-inventory"):
        return _run_update(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
