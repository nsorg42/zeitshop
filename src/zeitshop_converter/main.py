from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import sys

from .conversion import convert_diamond_file
from .core import ConversionOptions, ImageArchiveOptions
from .gui import run_gui
from .io import (
    archive_diamondseven_images,
    diagnose_image_matches,
    read_diamond_file,
    write_error_csv,
    write_match_diagnostics,
    write_wix_csv,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser used by both script and module entrypoints."""

    parser = argparse.ArgumentParser(prog="zeitshop-converter")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="start the desktop GUI")

    convert = sub.add_parser("convert", help="convert a DIAMOND CSV into Wix import CSV")
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
    convert.add_argument("--default-visible", action="store_true", help="set visible=TRUE by default")
    convert.add_argument(
        "--inventory-mode",
        choices=("numeric", "stock"),
        default="numeric",
        help="numeric => write quantities, stock => IN_STOCK/OUT_OF_STOCK",
    )
    convert.add_argument("--handle-prefix", default="ds-", help="prefix used for generated handles")
    convert.add_argument(
        "--image-manifest",
        help="optional DiamondSEVEN image archive manifest CSV",
    )
    convert.add_argument(
        "--wix-site-id",
        help="optional Wix site ID used for automatic archived-image uploads",
    )
    convert.add_argument(
        "--wix-api-key",
        help="optional Wix API key used for automatic archived-image uploads",
    )
    convert.add_argument(
        "--wix-image-path",
        default="/zeitshop",
        help="target Media Manager folder path for uploaded images",
    )

    archive = sub.add_parser(
        "archive-images",
        help="download full-quality DiamondSEVEN article images into a local archive",
    )
    archive.add_argument("--output-dir", required=True, help="directory where image files should be stored")
    archive.add_argument("--manifest", required=True, help="path for generated manifest CSV")
    archive.add_argument(
        "--base-url",
        default=os.environ.get("DIAMONDSEVEN_BASE_URL", ""),
        help="DiamondSEVEN server base URL (or DIAMONDSEVEN_BASE_URL)",
    )
    archive.add_argument(
        "--partner-key",
        default=os.environ.get("DIAMONDSEVEN_PARTNER_KEY", ""),
        help="DiamondSEVEN PartnerKey (or DIAMONDSEVEN_PARTNER_KEY)",
    )
    archive.add_argument("--api-version", default="1.0", help="DiamondSEVEN API version query parameter")
    archive.add_argument(
        "--document-type",
        choices=("auto", "articles", "stock", "webstock"),
        default="auto",
        help="DiamondSEVEN export to use for image URLs; auto tries articles, stock, then webstock",
    )
    archive.add_argument(
        "--skip-webstock",
        action="store_true",
        help="do not attempt WebStock barcode metadata enrichment",
    )
    archive.add_argument(
        "--ca-bundle",
        help="optional PEM CA bundle used to verify DiamondSEVEN TLS certificates",
    )
    archive.add_argument(
        "--insecure-skip-tls-verify",
        action="store_true",
        help="trial-only fallback: disable TLS certificate verification for DiamondSEVEN downloads",
    )

    diagnose = sub.add_parser(
        "diagnose-image-matches",
        help="compare a DIAMOND CSV against a DiamondSEVEN image manifest",
    )
    diagnose.add_argument("--diamond", required=True, help="path to DIAMOND CSV")
    diagnose.add_argument("--manifest", required=True, help="path to DiamondSEVEN image manifest CSV")
    diagnose.add_argument("--output", help="optional CSV path for the diagnostic report")

    return parser


def _run_convert(args: argparse.Namespace) -> int:
    """Execute CLI conversion mode and write output files."""

    wix_site_id = args.wix_site_id or os.environ.get("ZEITSHOP_WIX_SITE_ID", "")
    wix_api_key = args.wix_api_key or os.environ.get("ZEITSHOP_WIX_API_KEY", "")
    image_archive = None
    if args.image_manifest:
        image_archive = ImageArchiveOptions(
            enabled=True,
            manifest_path=args.image_manifest,
            wix_site_id=wix_site_id,
            wix_api_key=wix_api_key,
            wix_file_path=args.wix_image_path,
        )
    options = ConversionOptions(
        default_visible=args.default_visible,
        numeric_inventory=args.inventory_mode == "numeric",
        handle_prefix=args.handle_prefix,
        image_archive=image_archive,
    )

    batch = convert_diamond_file(
        diamond_csv=args.diamond,
        wix_template_csv=args.template,
        options=options,
        progress_callback=print if image_archive and image_archive.enabled else None,
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


def _run_archive_images(args: argparse.Namespace) -> int:
    """Download full-quality DiamondSEVEN article pictures."""

    if not args.base_url:
        raise ValueError("Missing DiamondSEVEN base URL. Use --base-url or DIAMONDSEVEN_BASE_URL.")
    if not args.partner_key:
        raise ValueError("Missing DiamondSEVEN PartnerKey. Use --partner-key or DIAMONDSEVEN_PARTNER_KEY.")

    report = archive_diamondseven_images(
        base_url=args.base_url,
        partner_key=args.partner_key,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        api_version=args.api_version,
        document_type=args.document_type,
        include_webstock=not args.skip_webstock,
        ca_bundle=args.ca_bundle,
        insecure_skip_tls_verify=args.insecure_skip_tls_verify,
        progress_callback=print,
    )
    print(f"Downloaded images: {report.downloaded}")
    print(f"Skipped existing images: {report.skipped}")
    print(f"Failed downloads: {report.failed}")
    print(f"Duplicate URLs: {report.duplicate_urls}")
    print(f"Articles without pictures: {report.missing_pictures}")
    print(f"Articles without usable metadata: {report.unmatched_metadata}")
    print(f"Manifest: {Path(args.manifest).expanduser()}")
    return 0


def _run_diagnose_image_matches(args: argparse.Namespace) -> int:
    """Run CSV-to-manifest image match diagnostics."""

    records = read_diamond_file(args.diamond)
    diagnostics = diagnose_image_matches(records, args.manifest)
    counts = Counter(diagnostic.status for diagnostic in diagnostics)
    if args.output:
        write_match_diagnostics(args.output, diagnostics)
        print(f"Diagnostic CSV: {args.output}")
    print(f"Rows checked: {len(diagnostics)}")
    print(f"Matched: {counts.get('matched', 0)}")
    print(f"Missing: {counts.get('missing', 0)}")
    print(f"Ambiguous: {counts.get('ambiguous', 0)}")
    print(f"Matched without images: {counts.get('matched_without_images', 0)}")
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

    if args.command == "archive-images":
        return _run_archive_images(args)

    if args.command == "diagnose-image-matches":
        return _run_diagnose_image_matches(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
