# Zeitshop Converter

Zeitshop Converter is a local desktop tool for converting DIAMOND product exports into Wix import CSV files.

It is built for a simple workflow:

1. Select a DIAMOND `.csv` or `.xlsx` export.
2. Convert it into the Wix product CSV format.
3. Review warnings or errors.
4. Export the final Wix-ready file.

The project is a local Python application with a Tkinter GUI and an optional CLI. There is no server component.

## Functionality Overview

- Reads DIAMOND exports from `.csv` and `.xlsx`
- Detects CSV encoding and delimiter automatically
- Normalizes incoming DIAMOND columns into a fixed internal schema
- Merges duplicate products by article number, with reference as fallback
- Sums inventory when duplicate rows represent the same product
- Maps DIAMOND data into the Wix product CSV structure
- Uses a built-in Wix template header by default
- Validates important Wix fields and records row-level warnings/errors
- Lets users export the main Wix CSV and a separate issue report from the GUI
- Supports both GUI and CLI usage

## Requirements

- Python 3.10 or newer
- Windows 10/11 for the packaged desktop build

## Installation On Windows

You have two practical options.

### Option 1: Use the packaged app

If you already have a built zip package:

1. Extract `ZeitshopConverter-windows.zip`
2. Open the extracted folder
3. Run `ZeitshopConverter.exe`

Notes:

- This is an unsigned internal app, so Windows SmartScreen may show a warning on first launch.
- No separate Python installation is needed for the packaged app.

### Option 2: Build the Windows app from this repository

Install Python 3.10+ first.

Then open `cmd.exe` in the repository root and run:

```bat
scripts\build_windows.cmd
```

Or in PowerShell:

```powershell
./scripts/build_windows.ps1
```

This produces:

- `dist\ZeitshopConverter\`
- `dist\ZeitshopConverter-windows.zip`

The zip file is the mail-ready artifact.

## Running From Source

### Windows

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[gui,dev]
python -m zeitshop_converter.main gui
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[gui,dev]
PYTHONPATH=src python -m zeitshop_converter.main gui
```

## CLI Usage

Convert a DIAMOND export from the command line:

```bash
python -m zeitshop_converter.main convert \
  --diamond "input.xlsx" \
  --output "out/wix_import.csv" \
  --error-output "out/issues.csv"
```

Useful options:

- `--default-visible` sets `visible=TRUE`
- `--inventory-mode stock` writes `IN_STOCK` / `OUT_OF_STOCK`
- `--handle-prefix ds-` controls generated handles
- `--template path/to/template.csv` uses a custom Wix template header

## GUI Usage

Start the desktop app:

```bash
python -m zeitshop_converter.main gui
```

In the GUI you can:

- Select a DIAMOND `.csv` or `.xlsx` file
- Run the conversion directly
- Review row counts, warnings, and errors
- Search and sort the preview table
- Export the Wix CSV
- Export issue reports for errors and warnings

## Development

Install development dependencies:

```bash
pip install -e .[gui,dev]
```

Run tests:

```bash
pytest -q
```

## Project Structure

```text
src/zeitshop_converter/
  core/    business rules, mapping, validation, normalization
  io/      file readers, template loading, CSV writers
  gui/     Tkinter desktop application
  main.py  CLI and GUI entrypoint
```

## Output Files

The app can generate:

- a Wix import CSV containing valid rows
- an issue CSV containing row-level warnings and errors

## Notes

- The built-in Wix template header is used unless you explicitly pass a custom template in CLI mode.
- The project is designed for local conversion workflows and does not require internet access during normal use.
