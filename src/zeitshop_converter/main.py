from __future__ import annotations
import argparse
import sys

from .conversion import convert_diamond_file
from .core import ConversionOptions
from .gui import run_gui
from .io import write_error_csv, write_wix_csv


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser used by both script and module entrypoints."""

    parser = argparse.ArgumentParser(prog="zeitshop-converter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="start the desktop GUI")

    convert = sub.add_parser("convert", help="convert a DIAMOND CSV/XLSX into Wix import CSV")
    convert.add_argument("--diamond", required=True, help="path to DIAMOND CSV/XLSX")
    convert.add_argument(
        "--template",
        help="optional path to Wix template CSV (default present)",
    )
    convert.add_argument("--output", required=True, help="path for generated Wix CSV")
    convert.add_argument("--error-output", help="optional path for error rows CSV")
    convert.add_argument("--default-visible", action="store_true", help="set visible=TRUE by default")
    convert.add_argument(
        "--inventory-mode",
        choices=("numeric", "stock"),
        default="numeric",
        help="numeric => write quantities, stock => IN_STOCK/OUT_OF_STOCK",
    )
    convert.add_argument("--handle-prefix", default="ds-", help="prefix used for generated handles")

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

    error_rows = batch.error_rows
    if args.error_output:
        write_error_csv(args.error_output, error_rows)

    print(f"Converted rows: {len(batch.results)}")
    print(f"Valid rows: {output_rows}")
    print(f"Rows with errors: {len(error_rows)}")
    print(f"Rows with warnings: {batch.warning_count}")

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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
