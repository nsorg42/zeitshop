# Zeitshop Converter

Zeitshop Converter is a local Python application that turns DIAMOND CSV exports into Wix product import CSVs.

It is purpose-built for a DIAMOND-to-Wix workflow: parents export inventory rows from DIAMOND, the converter maps them into Wix's import format, and the generated CSV can be uploaded to Wix Stores.

## What It Does

- Reads DIAMOND-style `.csv` exports
- Detects CSV encoding and delimiter automatically
- Normalizes DIAMOND columns into a fixed internal product schema
- Merges duplicate product rows by article number, with reference as fallback
- Aggregates inventory when duplicate rows describe the same product
- Maps source data into Wix `PRODUCT` rows
- Validates required Wix fields and writes a German issue report
- Can match products to a local full-quality DiamondSEVEN image archive
- Can upload matched archived images to Wix Media Manager and emit Wix `MEDIA` rows

## Scope And Limitations

- `.xlsx` exports and embedded Excel thumbnail extraction are no longer supported.
- The image workflow expects a local archive downloaded from the DiamondSEVEN Data Exchange API.
- Private customer exports, credentials, downloaded images, and large sample files are intentionally not included in this repository.
- Back up the local image archive separately; it is not stored in git.

## Requirements

- Python 3.10 or newer
- Tkinter available in the Python installation if you want to use the GUI
- Windows if you want the packaged desktop build

## Installation

Install the application from source:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[gui]
```

Install development dependencies as well if you want to run the test suite:

```bash
pip install -e .[gui,dev]
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Quick Start

### GUI

Launch the desktop app:

```bash
python -m zeitshop_converter.main gui
```

The GUI lets you:

- choose a DIAMOND CSV export
- run the conversion immediately
- review counts, warnings, and errors
- edit selected product fields before export
- download the Wix CSV
- download a German issue report
- configure an optional local image archive manifest and Wix credentials

### CLI

Convert a DIAMOND CSV export into a Wix CSV:

```bash
python -m zeitshop_converter.main convert \
  --diamond input.csv \
  --output out/wix_import.csv \
  --issues-output out/issues.csv
```

Useful options:

- `--template path/to/template.csv`: use a custom Wix template header instead of the built-in one
- `--default-visible`: write `visible=TRUE`
- `--inventory-mode stock`: write `IN_STOCK` / `OUT_OF_STOCK` instead of numeric inventory
- `--handle-prefix ds-`: change the generated handle prefix
- `--image-manifest path/to/manifest.csv`: match rows to the local DiamondSEVEN image archive
- `--wix-site-id` and `--wix-api-key`: enable automatic upload of matched local images to Wix Media Manager
- `--wix-image-path /zeitshop`: control the target folder path inside Wix Media Manager

Environment variables are supported for Wix credentials:

```bash
export ZEITSHOP_WIX_SITE_ID="your-site-id"
export ZEITSHOP_WIX_API_KEY="your-api-key"
```

Example with archived image upload:

```bash
python -m zeitshop_converter.main convert \
  --diamond input.csv \
  --image-manifest ~/.zeitshop_converter/diamond_images/manifest.csv \
  --output out/wix_import.csv \
  --issues-output out/issues.csv
```

## One-Time Image Archive

During a DiamondSEVEN API trial, download full-quality article images into a local archive:

```bash
export DIAMONDSEVEN_BASE_URL="https://server.diamondseven.swiss:10555"
export DIAMONDSEVEN_PARTNER_KEY="your-partner-key"

python -m zeitshop_converter.main archive-images \
  --output-dir ~/.zeitshop_converter/diamond_images \
  --manifest ~/.zeitshop_converter/diamond_images/manifest.csv
```

The archive command:

- calls the DiamondSEVEN `articles` export
- attempts `webstock` enrichment for barcode metadata
- downloads `ArticlePictures[].PictureURL`
- stores files under `files/<article_id>/`
- writes `manifest.csv` with article IDs, references, barcodes, source URLs, local paths, SHA-256 hashes, and byte sizes
- skips already-downloaded files when the manifest and hash still match

You can also pass credentials directly:

```bash
python -m zeitshop_converter.main archive-images \
  --base-url https://server.diamondseven.swiss:10555 \
  --partner-key your-partner-key \
  --output-dir ~/.zeitshop_converter/diamond_images \
  --manifest ~/.zeitshop_converter/diamond_images/manifest.csv
```

## Image Match Diagnostics

Before using images in production, compare a current DIAMOND CSV export against the manifest:

```bash
python -m zeitshop_converter.main diagnose-image-matches \
  --diamond input.csv \
  --manifest ~/.zeitshop_converter/diamond_images/manifest.csv \
  --output out/image_match_diagnostics.csv
```

Matching order:

1. `Artikel Nr` equals API `ArticleId`
2. `Artikel Nr` equals API `Reference`
3. `Referenz` equals API `Reference`
4. `Referenz` equals API `Barcode`

Rows with no match or ambiguous matches are exported without media and appear as warnings in the issue report during conversion.

## Output Files

Depending on the workflow, the converter can generate:

- a Wix import CSV with valid `PRODUCT` rows
- additional Wix `MEDIA` rows for matched archived product images
- a German issue report CSV containing row-level errors and warnings
- a DiamondSEVEN image archive manifest
- an image match diagnostic CSV

## Windows Build

To package the GUI as a Windows desktop app:

```powershell
./scripts/build_windows.ps1
```

Or from `cmd.exe`:

```bat
scripts\build_windows.cmd
```

The build produces:

- `dist\ZeitshopConverter\`
- `dist\ZeitshopConverter-windows.zip`

## Development

Run the test suite:

```bash
pytest -q
```

Project layout:

```text
src/zeitshop_converter/
  core/    conversion rules, normalization, validation, mapping
  io/      CSV readers, writers, template loading, image archive/upload helpers
  gui/     Tkinter desktop application
  main.py  CLI and GUI entrypoint
```

## Notes

- The built-in Wix template header is used unless you explicitly pass a custom template.
- Conversion without archived image upload is fully local.
- Image uploads require Wix credentials and network access.
