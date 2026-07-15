# Zeitshop Converter

Zeitshop Converter is a local Python application that turns DIAMOND CSV exports into Wix product import CSVs.

The converter is intentionally small: it reads DIAMOND-style `.csv` files, maps product rows into Wix's CSV structure, validates the generated product rows, writes an optional German issue report, and can update inventory in an existing Wix export from a newer DIAMOND inventory CSV.

## What It Does

- Reads DIAMOND `.csv` exports
- Detects CSV encoding and delimiter automatically
- Normalizes DIAMOND columns into a fixed internal product schema
- Merges duplicate product rows by article number, with reference as fallback
- Aggregates inventory when duplicate rows describe the same product
- Maps source data into Wix `PRODUCT` rows
- Validates required Wix fields
- Writes a German issue report for errors and warnings
- Updates inventory and availability text in an existing Wix product export from a newer DIAMOND inventory export
- Checks update exports against a configurable fixed brand list
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
- switch to update mode, choose a Wix product export plus a newer DIAMOND inventory CSV, review changes, and save the updated Wix CSV
- edit the fixed brand list used by update-mode safety checks in the settings window

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

Update a Wix product export with a newer DIAMOND inventory CSV:

```bash
python -m zeitshop_converter.main update \
  --wix-export catalog_products.csv \
  --diamond lager.csv \
  --output out/catalog_products_inventory_update.csv
```

Update mode changes the Wix `inventory` column and the availability sentence in `plainDescription` for configured brands. Matched products get the summed DIAMOND quantity and the current Am Bogen/Droz availability text from positive-stock DIAMOND rows. Wix products from configured brands that are missing from the DIAMOND export are set to `0` and their known availability sentence is removed. Wix product rows whose brand is not in the configured list are treated as unmanaged additional-import products and are preserved unchanged.

DIAMOND products missing from the Wix export are converted into new Wix product rows and shown at the top of the update preview as `Neu`. These new products should be checked manually in Wix after import. In update mode, the `Beschreibung hinzufügen` button can load a DIAMOND report CSV and adds report descriptions only to those new rows.

Both files must contain at least one product for every configured brand. Brands outside the configured list in the DIAMOND update file are blocking safety errors.

The default brand list is stored in the package and copied on first use to:

```text
~/.zeitshop_converter/brands.txt
```

The GUI settings window can edit this runtime brand list.

## Output Files

The converter can generate:

- a Wix import CSV with valid `PRODUCT` rows
- a German issue report CSV containing row-level errors and warnings

## Windows Installation

For a normal Windows computer with Python 3.10 or newer installed, run this from the repository folder:

```bat
scripts\install_windows.cmd
```

The installer creates:

- `%LOCALAPPDATA%\ZeitshopConverter\`
- a desktop shortcut named `Zeitshop Converter`
- a Start Menu shortcut named `Zeitshop Converter`
- a CLI launcher at `%LOCALAPPDATA%\ZeitshopConverter\bin\zeitshop-converter.cmd`

To remove the installed app:

```bat
scripts\uninstall_windows.cmd
```

To remove an old installation and install the current checkout again:

```bat
scripts\reinstall_windows.cmd
```

## Portable Windows Build

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
