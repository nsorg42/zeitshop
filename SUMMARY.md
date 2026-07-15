# Zeitshop Converter Repository Summary

## Purpose

`zeitshop-converter` is a local Python application for converting DIAMOND `.csv` exports into Wix product import CSV files. It also updates inventory in an existing Wix product export from a newer DIAMOND inventory CSV.

The application is intentionally focused on the shop workflow:

1. Convert DIAMOND product exports into Wix-compatible import CSV files.
2. Review validation warnings and errors in German.
3. Update inventory in a Wix export from a current DIAMOND inventory export.
4. Use either the Tkinter GUI or the CLI.

## Repository Layout

```text
.
├── README.md
├── SUMMARY.md
├── LICENSE
├── pyproject.toml
├── scripts/
│   ├── build_windows.cmd
│   ├── build_windows.ps1
│   ├── install_windows.cmd
│   ├── install_windows.ps1
│   ├── launch_gui.py
│   ├── reinstall_windows.cmd
│   ├── reinstall_windows.ps1
│   ├── uninstall_windows.cmd
│   └── uninstall_windows.ps1
├── src/zeitshop_converter/
│   ├── conversion.py
│   ├── inventory_update.py
│   ├── main.py
│   ├── core/
│   ├── gui/
│   └── io/
└── tests/
```

The source package uses the `src` layout configured in `pyproject.toml`. Tests live in `tests/` and are run with `pytest`.

## Package Metadata

`pyproject.toml` defines:

- package name: `zeitshop-converter`
- Python requirement: `>=3.10`
- runtime dependency: `charset-normalizer`
- optional GUI dependency: `sv-ttk`
- optional Windows build dependency: `pyinstaller`
- optional development dependency: `pytest`

The installed console script is:

```toml
zeitshop-converter = "zeitshop_converter.main:main"
```

## User Workflows

### GUI

The GUI starts with either command:

```bash
zeitshop-converter
zeitshop-converter gui
```

It has two modes:

- `Import`: choose a DIAMOND CSV, convert it, optionally edit selected fields, save the Wix import CSV, and save issue reports.
- `Update`: choose a Wix product export plus a newer DIAMOND inventory CSV, update inventory and availability text, and save the updated Wix CSV after fixed-brand safety checks pass.
- `Einstellungen`: configure import defaults and edit the fixed update-mode brand list.

### CLI Conversion

```bash
zeitshop-converter convert \
  --diamond input.csv \
  --output out/wix_import.csv \
  --issues-output out/issues.csv
```

Useful conversion options:

- `--template path/to/template.csv`
- `--default-visible`
- `--inventory-mode numeric|stock`
- `--handle-prefix ds-`

### CLI Inventory Update

```bash
zeitshop-converter update \
  --wix-export catalog_products.csv \
  --diamond lager.csv \
  --output out/catalog_products_inventory_update.csv
```

`update-inventory` is accepted as an alias for `update`.

The update mode matches configured-brand Wix product rows by `sku` against DIAMOND `Artikel Nr`, updates the Wix `inventory` column, and replaces known availability sentences in `plainDescription`. Matching rows get the summed DIAMOND quantity and current Am Bogen/Droz availability from positive-stock DIAMOND rows; configured-brand Wix products missing from the DIAMOND update are set to `0` and lose known availability text; unmanaged Wix rows whose brand is not configured are preserved unchanged; DIAMOND products missing from the Wix export are converted into new Wix product rows.

## Conversion Flow

```text
main.py / gui.app
  ↓
conversion.convert_diamond_file(...)
  ↓
io.read_diamond_file(...)
  ↓
core.convert_records(...)
  ↓
core.map_diamond_to_wix_row(...)
  ↓
core.validate_wix_row(...)
  ↓
core.ensure_unique_product_barcodes(...)
  ↓
io.write_wix_csv(...)
io.write_issue_csv(...)
```

The main data containers are:

- `DiamondRecord`: canonicalized source row.
- `WixRowResult`: mapped Wix product row plus validation issues.
- `ConversionBatch`: all conversion results and convenience counts.
- `InventoryUpdateResult`: one Wix product row after inventory matching.
- `InventoryUpdateIssueRow`: one safety or unmatched-row issue for update reports.
- `InventoryUpdateBatch`: updated rows, issue rows, blocking status, and match/change/set-to-zero/new-product counts.

## CSV Handling

DIAMOND files are read through `io/diamond_reader.py`. The reader detects encoding and delimiter and normalizes known DIAMOND columns into a fixed internal schema.

Wix output uses either:

- the built-in header in `io/wix_template.py`, or
- a user-provided Wix template CSV header.

Wix CSV writing is centralized in `io/wix_writer.py` and preserves the configured header order.

## Mapping And Validation

Mapping lives in `core/mapping.py`.

Key behaviors:

- product handles are generated from `Artikel Nr`, then `Referenz`, then source row fallback;
- product names are built from brand, product line, and short description while avoiding repeated words;
- duplicate handles are deduplicated with numeric suffixes;
- inventory can be numeric or stock enum during import conversion;
- category slugs are normalized from DIAMOND category values;
- branch availability sentences are generated for known branches.

Validation lives in `core/validation.py`.

Required Wix fields include:

- `fieldType`
- `name`
- `visible`
- `price`
- `inventory`
- `sku`

Validation distinguishes blocking errors from warnings so usable rows can still be exported.

## Inventory Update

`inventory_update.py` powers both GUI update mode and CLI update mode. The fixed brand list is loaded from `~/.zeitshop_converter/brands.txt`, which is created from packaged defaults on first use and can be edited in GUI settings.

The updater:

- reads a Wix product export CSV;
- reads a newer DIAMOND inventory CSV;
- sums quantities by `Artikel Nr`;
- merges positive-stock branches by `Artikel Nr`;
- updates matching Wix product rows by `sku`;
- sets unmatched Wix product rows to `0`;
- converts DIAMOND products missing from Wix into new product rows;
- pins new product rows to the top of the GUI update preview;
- can enrich only those new rows from a DIAMOND report CSV through `Beschreibung hinzufügen`;
- replaces old or new known availability sentences in `plainDescription` with the current canonical wording;
- blocks export when either file is missing a configured brand or the DIAMOND update contains a brand outside the configured list;
- preserves unmanaged Wix rows whose brand is outside the configured list;
- preserves non-product rows and every Wix field except `inventory` and `plainDescription` unchanged.

## Windows Installation

For normal Windows use from a source checkout:

```bat
scripts\install_windows.cmd
```

The installer creates a non-editable local installation under:

```text
%LOCALAPPDATA%\ZeitshopConverter\
```

It also creates Desktop and Start Menu shortcuts for the GUI and a CLI launcher at:

```text
%LOCALAPPDATA%\ZeitshopConverter\bin\zeitshop-converter.cmd
```

Uninstall with:

```bat
scripts\uninstall_windows.cmd
```

Replace an old installation with the current checkout by running:

```bat
scripts\reinstall_windows.cmd
```

For a portable PyInstaller bundle, build on Windows with:

```powershell
.\scripts\build_windows.ps1
```

The portable build writes:

- `dist\ZeitshopConverter\`
- `dist\ZeitshopConverter-windows.zip`

## Verification

Recommended checks:

```bash
python -m compileall -q src tests
pytest -q
```

For CLI smoke testing from a checkout without installing first, set `PYTHONPATH=src` on Linux/macOS or install the package into a virtual environment.
