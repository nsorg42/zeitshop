# Zeitshop Converter

Zeitshop Converter is a local Python application that turns DIAMOND product exports into Wix product import CSVs.

The converter expects DIAMOND-style `.csv` and `.xlsx` exports, maps them into Wix's CSV structure, and can optionally export product images into Wix Media Manager for automated migration.

## What It Does

- Reads DIAMOND exports from `.csv` and `.xlsx`
- Detects CSV encoding and delimiter automatically
- Normalizes DIAMOND columns into a fixed internal product schema
- Merges duplicate product rows by article number, with reference as fallback
- Aggregates inventory when duplicate rows describe the same product
- Maps source data into Wix `PRODUCT` rows
- Validates required Wix fields and writes a separate issue report
- Resolves product images from:
  - explicit values in the DIAMOND `Bild` column
  - a local image directory
  - embedded images inside `.xlsx` exports
- Optionally uploads local images to Wix Media Manager and emits Wix `MEDIA` rows
- Supports both a Tkinter GUI and a CLI

## Scope And Limitations

- The mapping is purpose-built for a specific DIAMOND-to-Wix workflow, not a generic ETL framework.
- Private customer exports and large sample files are intentionally not included in this repository.

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

- choose a DIAMOND export
- run the conversion immediately
- review counts, warnings, and errors
- download the Wix CSV
- download a German issue report
- configure optional image migration settings

### CLI

Convert a DIAMOND export into a Wix CSV:

```bash
python -m zeitshop_converter.main convert \
  --diamond input.xlsx \
  --output out/wix_import.csv \
  --issues-output out/issues.csv
```

Useful options:

- `--template path/to/template.csv`: use a custom Wix template header instead of the built-in one
- `--default-visible`: write `visible=TRUE`
- `--inventory-mode stock`: write `IN_STOCK` / `OUT_OF_STOCK` instead of numeric inventory
- `--handle-prefix ds-`: change the generated handle prefix
- `--images-dir path/to/images`: scan a local directory recursively for matching product images
- `--export-embedded-images`: extract embedded workbook images from `.xlsx` inputs and write a mapping CSV
- `--image-export-dir path/to/export`: control where extracted workbook images are written
- `--wix-site-id` and `--wix-api-key`: enable automatic upload of local images to Wix Media Manager
- `--wix-image-path /zeitshop`: control the target folder path inside Wix Media Manager

Environment variables are supported for Wix credentials:

```bash
export ZEITSHOP_WIX_SITE_ID="your-site-id"
export ZEITSHOP_WIX_API_KEY="your-api-key"
```

Example with automatic image upload:

```bash
python -m zeitshop_converter.main convert \
  --diamond input.xlsx \
  --images-dir product_images \
  --output out/wix_import.csv \
  --issues-output out/issues.csv
```

## Embedded XLSX Images

If a DIAMOND `.xlsx` export contains embedded worksheet images, you can extract them without running a full conversion:

```bash
python -m zeitshop_converter.main export-images \
  --diamond input.xlsx \
  --output-dir out/extracted_images \
  --mapping-output out/image_mapping.csv
```

This writes:

- the extracted image files
- a CSV showing which source row each extracted image was matched to

When image migration is enabled during conversion, extracted workbook images are treated like normal local image files and can be uploaded to Wix automatically.

## Output Files

Depending on the workflow, the converter can generate:

- a Wix import CSV with valid `PRODUCT` rows
- additional Wix `MEDIA` rows for resolved product images
- a German issue report CSV containing row-level errors and warnings
- an extracted image directory and image-mapping CSV for `.xlsx` image inspection

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

There is also a GitHub Actions workflow in `.github/workflows/build-windows-app.yml` for manual Windows builds.

## Development

Run the test suite:

```bash
pytest -q
```

GitHub Actions now also runs `.github/workflows/ci.yml` automatically on every push and pull request. That workflow installs the project with development dependencies and runs `pytest`, so GitHub will show whether the branch is green before you merge it.

Project layout:

```text
src/zeitshop_converter/
  core/    conversion rules, normalization, validation, mapping
  io/      readers, writers, template loading, image extraction/upload helpers
  gui/     Tkinter desktop application
  main.py  CLI and GUI entrypoint
```

## Notes

- The built-in Wix template header is used unless you explicitly pass a custom template.
- Image uploads require network access. Conversion without Wix uploads is fully local.
- Embedded image extraction works with the first worksheet in the workbook, which matches the converter's main import workflow.
