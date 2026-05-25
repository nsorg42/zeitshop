# Zeitshop Converter

Zeitshop Converter is a local Python application that turns DIAMOND CSV exports into Wix product import CSVs.

The converter is intentionally small: it reads DIAMOND-style `.csv` files, maps product rows into Wix's CSV structure, validates the generated product rows, and writes an optional German issue report.

## What It Does

- Reads DIAMOND `.csv` exports
- Detects CSV encoding and delimiter automatically
- Normalizes DIAMOND columns into a fixed internal product schema
- Merges duplicate product rows by article number, with reference as fallback
- Aggregates inventory when duplicate rows describe the same product
- Maps source data into Wix `PRODUCT` rows
- Validates required Wix fields
- Writes a German issue report for errors and warnings
- Supports both a Tkinter GUI and a CLI

## Scope

- `.xlsx` exports are not supported.
- Image extraction, image download, API access, and Wix image upload are not supported.
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

- choose a DIAMOND CSV export
- run the conversion immediately
- review counts, warnings, and errors
- edit selected product fields before export
- download the Wix CSV
- download a German issue report

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

## Output Files

The converter can generate:

- a Wix import CSV with valid `PRODUCT` rows
- a German issue report CSV containing row-level errors and warnings

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
  io/      CSV readers, writers, template loading
  gui/     Tkinter desktop application
  main.py  CLI and GUI entrypoint
```

## Notes

- The built-in Wix template header is used unless you explicitly pass a custom template.
- Conversion is fully local.
