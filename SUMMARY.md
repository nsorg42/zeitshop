# Zeitshop Converter Repository Summary

## High-Level Purpose

`zeitshop-converter` is a local Python application for converting DIAMOND product exports into Wix product import CSV files. It supports both `.csv` and `.xlsx` DIAMOND exports, normalizes the source data into a small internal product schema, maps those products into Wix-compatible rows, validates the output, and optionally resolves product images into Wix `MEDIA` rows.

The project is not a generic ETL system. It is a focused DIAMOND-to-Wix converter with assumptions baked around the source columns used by DIAMOND exports and the Wix CSV import format expected by the target shop.

The package exposes three user-facing workflows:

1. A Tkinter GUI launched with `zeitshop-converter gui` or no command.
2. A CLI conversion command launched with `zeitshop-converter convert`.
3. A CLI embedded-image extraction command launched with `zeitshop-converter export-images`.

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
│   └── launch_gui.py
├── src/
│   └── zeitshop_converter/
│       ├── __init__.py
│       ├── conversion.py
│       ├── main.py
│       ├── core/
│       ├── gui/
│       └── io/
└── tests/
```

The source package is under `src/zeitshop_converter`, using the common `src` layout configured in `pyproject.toml`. Tests live in `tests/` and are run with `pytest`.

## Package Metadata And Dependencies

`pyproject.toml` defines the package as `zeitshop-converter`, version `0.1.0`, requiring Python `>=3.10`.

Runtime dependencies:

- `charset-normalizer`: used as a fallback for CSV encoding detection.
- `openpyxl`: used for reading XLSX files when available.

Optional dependency groups:

- `gui`: installs `sv-ttk`, an optional modern Tk theme.
- `windows-build`: installs `pyinstaller` for packaged Windows builds.
- `dev`: installs `pytest`.

The console script entrypoint is:

```toml
zeitshop-converter = "zeitshop_converter.main:main"
```

That means installed users can run `zeitshop-converter ...`, while source users can also run `python -m zeitshop_converter.main ...`.

## End-To-End Conversion Flow

The central conversion flow is:

```text
CLI / GUI
  ↓
zeitshop_converter.main or zeitshop_converter.gui.app
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
io.attach_media_rows(...)   optional
  ↓
io.write_wix_csv(...)       final Wix import file
io.write_issue_csv(...)     optional German issue report
```

The converter uses a deliberately small internal representation:

- `DiamondRecord`: one canonicalized source row from a DIAMOND file.
- `WixRowResult`: one mapped Wix product row plus warnings, errors, and optional media rows.
- `ConversionBatch`: all row results and helper properties for valid rows, issue rows, counts, and rows to write.

This keeps parsing, mapping, validation, and output responsibilities separated.

## Data Model

The canonical DIAMOND source schema is defined in `io/diamond_reader.py` as:

```text
Bild
Filiale
Kategorie
Warengruppe
Marke
Produktlinie
Artikel Nr
Kurzbeschreibung
Referenz
Menge
Einstand
Verkauf
```

Every input row is projected into those fields, even if the source file has extra columns. Unknown columns are ignored. Missing canonical fields become empty strings.

The mapped Wix output schema comes from either:

- the built-in Wix template header in `io/wix_template.py`, or
- a user-supplied template CSV header.

The required Wix columns are:

```text
handle
fieldType
name
visible
price
inventory
sku
```

Image migration additionally requires a `media` column.

## Duplicate Row Merge Logic

Duplicate source rows are handled in `core/pipeline.py`.

Rows are grouped by product identity:

1. `Artikel Nr`
2. `Referenz`
3. fallback `row-{source_row}`

Rows with the same identity are merged only when their stable product fields match after normalization. The allowed differences are:

- `Filiale`
- `Menge`
- `Bild`

When duplicate rows are compatible:

- quantities from `Menge` are parsed and summed,
- image references from `Bild` are merged with stable order and deduplication,
- the first row's source row remains the representative row.

When duplicate rows are not compatible:

- they are not fully merged,
- compatible subgroups may still be merged,
- each resulting row receives a warning explaining that the duplicate identity was not merged and why.

Fields that can block safe merging if invalid are:

- `Einstand`
- `Verkauf`
- `Menge`

This prevents bad numeric values from being hidden by a merge.

## Mapping Rules

DIAMOND rows are mapped to Wix product rows in `core/mapping.py`.

The mapper starts by creating an output dictionary with every template column set to `""`. It then fills a focused subset:

| Wix column | Source / behavior |
| --- | --- |
| `fieldType` | Always `PRODUCT` |
| `handle` | Generated from `Artikel Nr`, else `Referenz`, else source row |
| `name` | Built from `Marke`, `Produktlinie`, and `Kurzbeschreibung` |
| `visible` | `TRUE` or `FALSE` from options |
| `brand` | DIAMOND `Marke` |
| `plainDescription` | Composed from `Warengruppe` and `Kategorie` |
| `sku` | `Artikel Nr`, falling back to `Referenz` |
| `barcode` | `Referenz`, if the output template has a `barcode` column |
| `price` | Parsed from `Verkauf` and formatted to 2 decimals |
| `cost` | Parsed from `Einstand` and formatted to 2 decimals |
| `inventory` | Numeric quantity or stock enum depending on options |

Handles are URL-safe and deduplicated. If the generated handle already exists, `-2`, `-3`, etc. are appended and a warning is attached.

Product names are built carefully to avoid repeated words and phrases. The name builder:

- tokenizes brand, product line, and short description,
- removes direct token repetition,
- handles simple plural duplication,
- detects repeated compound tokens like `OhrsteckerOhrstecker`,
- drops prefix overlap between later components and the already-built name,
- falls back to `Artikel Nr` or `product-{source_row}`,
- truncates names longer than 80 characters and emits a warning.

## Validation Rules

Validation happens in `core/validation.py`.

Product rows must satisfy:

- `fieldType` must be `PRODUCT`.
- `name` is required and must be at most 80 characters.
- `visible` must be `TRUE` or `FALSE`.
- `price` is required and must be numeric.
- `inventory` is required and must be `IN_STOCK`, `OUT_OF_STOCK`, or an integer.
- `cost`, if present, must be numeric with at most 9 whole digits and at most 2 decimal places.

Warnings are emitted for:

- `sku` longer than 40 characters,
- `brand` longer than 50 characters.

Validation issues use two severities:

- `ERROR`: row is not exported as a product.
- `WARNING`: row may still be exported, but the issue report records the problem.

The pipeline also avoids duplicating error messages. If mapping already produced an error for a field, later validation errors for the same field are suppressed where appropriate.

## Barcode Handling

`core/barcodes.py` mutates final product rows to ensure non-empty barcodes are unique.

The main source of the barcode is DIAMOND `Referenz`. If two product rows share the same barcode, the later conflicting rows receive deterministic fallback candidates derived from:

1. SKU
2. handle
3. SKU or handle plus source row
4. `zs-{source_row}`

Candidates are capped to Wix's internal maximum of 40 characters. Existing unique barcodes are preserved.

This function is used twice:

- during normal pipeline conversion, after all products are mapped,
- during GUI export, after inline edits are merged back into product rows.

The second use matters because a user can edit the reference/barcode-like preview field before exporting.

## Image Migration Flow

Image migration lives mainly in `io/media_migration.py`.

It can resolve images from:

- remote HTTP/HTTPS URLs in DIAMOND `Bild`,
- explicit local file paths in `Bild`,
- local filenames or stems found under an image directory,
- fallback matches by `Artikel Nr` or `Referenz`,
- embedded XLSX images extracted into local files.

Image migration is enabled when `ImageMigrationOptions.enabled` is true. The CLI enables it if any image directory or Wix credential value is passed. The GUI exposes it as an advanced setting.

The media flow is:

```text
attach_media_rows(...)
  ↓
build image search roots
  ↓
index local image files with ImageLibrary
  ↓
for each conversion result:
    collect explicit URLs
    resolve local files
    optionally upload local files to Wix
    add warning issues for unresolved or unuploaded files
    create Wix MEDIA rows
```

Remote URLs are added directly as media URLs.

Local files require Wix upload credentials. If a local image is found but uploads are not configured, the converter emits a warning instead of silently ignoring the image.

Supported local image extensions include:

```text
.avif .bmp .gif .heic .heif .jpeg .jpg .png .tif .tiff .webp
```

### Local Image Lookup

`ImageLibrary` recursively indexes supported image files under the configured roots. It can match by:

- full filename,
- file stem,
- sanitized stem,
- stem prefix followed by `_` or `-`.

The roots include:

- configured image directory, if present,
- the source DIAMOND file's parent directory.

Duplicate roots and duplicate paths are deduplicated.

### Wix Uploads

`WixMediaClient` performs upload to Wix Media Manager using the Wix Site Media API.

The upload sequence is:

1. Check internet connectivity to `www.wixapis.com:443`.
2. Generate an upload URL via Wix.
3. PUT the binary image file to that URL.
4. Determine the Wix file ID from the response or upload URL.
5. Poll Wix until the uploaded file has a usable media URL.
6. Cache the result in `~/.zeitshop_converter/wix_media_cache.json`.

The cache key includes:

- Wix site ID,
- resolved local path,
- file size,
- file modification timestamp.

This avoids re-uploading unchanged files.

The client supports both raw API-key authorization and Bearer authorization fallback for authenticated requests.

### MEDIA Rows

For each resolved media URL, the converter creates a Wix row with:

- same `handle` as the product,
- `fieldType = MEDIA`,
- `media = <url>`,
- `mediaAltText`, if present in the template.

The `ConversionBatch.valid_rows` property emits each valid product row followed by its media rows. Products with errors are skipped together with their media rows.

## Embedded XLSX Images

Embedded XLSX image support is implemented in `io/xlsx_images.py` and integrated from `io/diamond_reader.py`.

The extractor reads the XLSX zip structure directly:

- workbook XML identifies the first sheet,
- sheet relationships identify drawing XML,
- drawing relationships identify media files,
- drawing anchors identify rows and columns,
- image files are copied from `xl/media/...` into an export directory.

Only images anchored before the first non-image product data column are considered product images. The matcher maps image anchors to product source rows, allowing small row offsets of `+1`, `-1`, `+2`, and `-2`.

Default extracted-image paths are under:

```text
~/.zeitshop_converter/xlsx_images/<workbook-stem>-<fingerprint>/
```

The fingerprint is derived from the workbook path, size, and modification timestamp.

When images are extracted during conversion, their exported paths are merged into the source row's `Bild` field. That makes embedded images flow through the same media migration logic as explicit local image paths.

There is also a standalone `export-images` CLI command that extracts embedded images and writes a mapping CSV with:

- `source_row`
- `artikel_nr`
- `referenz`
- `bild`

## Issue Reports

Issue reports are written by `io/error_writer.py`.

Despite the older function name `write_error_csv`, the current report includes both errors and warnings. `write_error_csv` is kept as a backwards-compatible alias for `write_issue_csv`.

The report is German-first. It writes source data columns first, followed by issue metadata:

```text
source_row
<source DIAMOND fields...>
problem_schwere
problem_feld
problem
```

Severity is translated:

- `ERROR` -> `Fehler`
- `WARNING` -> `Warnung`

Many known English messages are translated to German exactly or through regex-specific translation. Unknown messages are passed through unchanged.

## CLI Behavior

The CLI is defined in `main.py`.

### Default / GUI

If no subcommand is provided, the GUI starts:

```bash
zeitshop-converter
```

The explicit GUI command does the same:

```bash
zeitshop-converter gui
```

### Convert Command

The conversion command requires:

```bash
zeitshop-converter convert --diamond input.xlsx --output out/wix.csv
```

Important options:

- `--template`: custom Wix template header CSV.
- `--issues-output`: issue report CSV path.
- `--error-output`: hidden backwards-compatible alias for `--issues-output`.
- `--default-visible`: makes product rows `visible=TRUE`; default CLI behavior is `FALSE`.
- `--inventory-mode numeric|stock`: chooses numeric quantities or `IN_STOCK` / `OUT_OF_STOCK`.
- `--handle-prefix`: prefix for generated handles; default is `ds-`.
- `--images-dir`: scan a local image directory.
- `--export-embedded-images`: extract embedded XLSX images during conversion.
- `--image-export-dir`: target directory for extracted XLSX images and mapping.
- `--wix-site-id`: Wix site ID for uploads.
- `--wix-api-key`: Wix API key for uploads.
- `--wix-image-path`: Wix Media Manager folder path, default `/zeitshop`.

Wix credentials can also come from environment variables:

```text
ZEITSHOP_WIX_SITE_ID
ZEITSHOP_WIX_API_KEY
```

The command prints summary counts:

- converted rows,
- valid products,
- written CSV rows,
- rows with errors,
- rows with warnings.

### Export Images Command

The standalone image command requires an XLSX input:

```bash
zeitshop-converter export-images --diamond input.xlsx
```

Optional arguments:

- `--output-dir`
- `--mapping-output`

It extracts images and prints:

- extracted image directory,
- number of rows with images,
- image mapping CSV path.

## GUI Behavior

The GUI is implemented in `gui/app.py` as `ConverterApp`, a `tk.Tk` subclass.

It is German-first and centered around a simple workflow:

1. Select a DIAMOND `.csv` or `.xlsx` file.
2. Conversion starts immediately.
3. Results appear in a preview table.
4. User can download the Wix CSV.
5. User can download issue reports.
6. Advanced settings control visibility, handle prefix, output directory, and image migration.

The GUI stores settings in:

```text
~/.zeitshop_converter/gui_settings.json
```

Persisted settings include:

- handle prefix,
- default visibility,
- output directory,
- whether image migration is enabled,
- whether embedded XLSX images should be exported,
- image export directory,
- Wix site ID,
- Wix API key,
- Wix media path.

### Threading Model

Long-running conversion runs in a background daemon thread. The worker thread sends events into a `queue.Queue`; the Tk main loop polls the queue with `after(100, ...)`.

This avoids freezing the UI during:

- large file parsing,
- embedded image extraction,
- image resolution,
- Wix uploads.

Progress messages from media migration are passed through a callback and update the progress bar when they match the `Bilder current/total` pattern.

### Preview And Inline Edits

The GUI preview table shows:

- `Artikel Nr`
- `Name`
- `Marke`
- `Kurzbeschreibung`
- `Preis`
- `Einstand`
- `Referenznummer`

Rows are color-tagged:

- normal alternating rows,
- warning rows,
- error rows.

The table supports:

- free-text search,
- clickable column sorting,
- double-click inline edits.

Inline edits are not written directly into the original batch. They are stored in `_preview_overrides` keyed by source row. When exporting, overrides are merged into product rows and validated again.

If edited rows contain validation errors, export is blocked and the GUI shows the first few issues.

### Download Behavior

The GUI does not immediately write output files after conversion. Instead, it keeps `ConversionBatch` in memory and writes files only when the user chooses a save path.

Default output directory order:

1. configured output directory,
2. input file folder,
3. user home directory.

Default filenames:

- Wix CSV: `<input-stem>_wix_import.csv`
- all issues: `<input-stem>_issues.csv`
- errors only: `<input-stem>_fehler.csv`
- warnings only: `<input-stem>_warnungen.csv`

## Source File Breakdown

### `src/zeitshop_converter/__init__.py`

Package initializer.

Exports:

- `__version__`
- `convert_diamond_file`

It reads the installed distribution version with `importlib.metadata.version("zeitshop-converter")`. If the package is not installed, it falls back to `"0.1.0"`.

### `src/zeitshop_converter/main.py`

Command-line and module entrypoint.

Key functions:

- `_build_parser()`: builds the `argparse` command tree.
- `_run_convert(args)`: turns CLI arguments into `ConversionOptions`, calls `convert_diamond_file`, writes output files, and prints counts.
- `_run_export_images(args)`: validates XLSX input, extracts embedded images, writes image mapping CSV, and prints paths/counts.
- `main(argv=None)`: dispatches to GUI, conversion, or image export.

The default command is the GUI. This means `zeitshop-converter` and `zeitshop-converter gui` both start the desktop app.

### `src/zeitshop_converter/conversion.py`

High-level orchestration layer used by both CLI and GUI.

The main function is `convert_diamond_file(...)`.

Responsibilities:

- resolve active options,
- decide whether embedded XLSX images should be extracted,
- read DIAMOND input records,
- optionally write an embedded-image mapping CSV,
- load the Wix template header,
- call `core.convert_records`,
- optionally attach media rows.

This file intentionally keeps business logic out of the UI and CLI.

### `src/zeitshop_converter/core/__init__.py`

Convenience export module for core types and `convert_records`.

It exposes:

- `ConversionBatch`
- `ConversionOptions`
- `DiamondRecord`
- `ImageMigrationOptions`
- `Severity`
- `ValidationIssue`
- `WixRowResult`
- `convert_records`

### `src/zeitshop_converter/core/models.py`

Defines the core dataclasses and severity enum.

Important types:

- `Severity`: `ERROR` or `WARNING`.
- `ValidationIssue`: row-level problem metadata.
- `DiamondRecord`: canonical source row with `source_row` and source `data`.
- `ConversionOptions`: conversion flags like visibility, inventory mode, handle prefix, image migration.
- `ImageMigrationOptions`: image lookup/export/upload settings.
- `WixRowResult`: mapped product row, media rows, source data, and issues.
- `ConversionBatch`: full conversion result with helper properties.

`ConversionBatch.valid_rows` is the important writer-facing property: it returns only rows without errors, and includes each product's attached media rows.

### `src/zeitshop_converter/core/normalize.py`

Shared parsing and normalization helpers.

Functions:

- `normalize_text(value)`: trims and collapses whitespace.
- `parse_decimal(value)`: parses decimal numbers including Swiss formats and separators.
- `format_decimal(value, places=2)`: formats a decimal with fixed places.
- `parse_quantity(value)`: parses integer quantities and rejects fractional values.
- `normalize_inventory(value, numeric_inventory=True)`: converts quantity to numeric stock or stock enum.
- `make_handle(raw, prefix="ds-")`: creates a lower-case URL-safe handle.

This module is used throughout mapping, validation, reading, merging, and image lookup.

### `src/zeitshop_converter/core/mapping.py`

Maps one `DiamondRecord` into one Wix product row.

Key internals:

- `_extract_tokens(...)`: tokenizes product-name components.
- `_dedupe_compound_repeat(...)`: fixes merged repeated words.
- `_drop_prefix_overlap(...)`: avoids repeated component overlap.
- `_build_name(record)`: builds the Wix product name.
- `_build_plain_description(record)`: turns category/group fields into a simple description.
- `_dedupe_handle(...)`: guarantees unique handles.
- `map_diamond_to_wix_row(...)`: main row mapper.

It returns both the row dictionary and any mapping issues.

### `src/zeitshop_converter/core/pipeline.py`

Core batch conversion pipeline.

Key responsibilities:

- group duplicate rows by product identity,
- merge compatible duplicates,
- warn on incompatible duplicate groups,
- call the mapper for each resulting record,
- detect duplicate SKUs,
- validate mapped rows,
- rewrite duplicate barcodes,
- return a `ConversionBatch`.

Important helpers:

- `_record_identity(...)`
- `_merge_signature(...)`
- `_merge_blocker_fields(...)`
- `_conflicting_merge_fields(...)`
- `_merge_compatible_rows(...)`
- `_merge_records_by_identity(...)`
- `convert_records(...)`

This is the heart of the conversion logic.

### `src/zeitshop_converter/core/validation.py`

Validates Wix product rows after mapping and after GUI edits.

It focuses on the Wix import fields that this converter writes or depends on:

- field type,
- name,
- visibility,
- price,
- inventory,
- cost,
- SKU length,
- brand length.

It returns `ValidationIssue` objects rather than raising exceptions, so callers can produce issue reports and continue processing other rows.

### `src/zeitshop_converter/core/barcodes.py`

Ensures product barcode values are unique.

Main function:

- `ensure_unique_product_barcodes(products)`

It mutates product row dictionaries in place. Duplicate barcode groups are rewritten to deterministic fallback values while unique existing values are left untouched.

### `src/zeitshop_converter/io/__init__.py`

Convenience export module for IO helpers.

It re-exports DIAMOND readers, Wix writer/template helpers, issue writer functions, media migration functions, and XLSX image helpers.

### `src/zeitshop_converter/io/detect.py`

CSV encoding and dialect detection.

Functions:

- `_load_charset_normalizer()`: lazy optional import.
- `detect_encoding(raw_bytes)`: tries `utf-8-sig`, `utf-8`, `cp1252`, then `charset-normalizer`, then `latin1`.
- `sniff_dialect(sample_text, delimiters=";,\t")`: uses `csv.Sniffer`, falling back to semicolon.

`SemicolonDialect` is the fallback dialect for empty or un-sniffable files.

### `src/zeitshop_converter/io/diamond_reader.py`

Reads DIAMOND `.csv` and `.xlsx` files into canonical `DiamondRecord` objects.

Major responsibilities:

- define canonical columns and header aliases,
- normalize raw headers,
- convert cell values to text,
- detect and skip empty/footer rows,
- detect and skip repeated in-body header rows,
- read CSV files with detected encoding and delimiter,
- read XLSX files with `openpyxl` when available,
- fall back to direct XLSX XML parsing when `openpyxl` is unavailable,
- locate the likely header row in XLSX files,
- optionally extract embedded workbook images and merge paths into `Bild`.

Important functions:

- `read_diamond_csv(path)`
- `read_diamond_xlsx(path, extract_embedded_images=False, image_export_dir=None)`
- `read_diamond_file(path, ...)`

The XLSX fallback parser reads:

- shared strings,
- workbook relationships,
- first worksheet XML,
- cell references and scalar values.

This fallback keeps the reader functional even if `openpyxl` is missing, although `openpyxl` is declared as a dependency.

### `src/zeitshop_converter/io/wix_template.py`

Defines and loads Wix CSV headers.

Important constants:

- `DEFAULT_WIX_TEMPLATE_HEADER`
- `REQUIRED_COLUMNS`

Functions:

- `default_template_header()`: returns a copy of the built-in Wix header.
- `load_template_header(path=None)`: loads custom template or built-in header.

Custom templates are read as comma-separated CSV and validated for required columns.

### `src/zeitshop_converter/io/wix_writer.py`

Writes final Wix import CSV files.

Function:

- `write_wix_csv(path, header, rows)`

It creates parent directories, writes UTF-8 CSV, preserves exact header order, ignores extra row keys, and returns the number of rows written.

### `src/zeitshop_converter/io/error_writer.py`

Writes German issue report CSVs.

Functions:

- `write_issue_csv(path, issue_rows)`
- `write_error_csv(path, error_rows)`

The latter is only an alias kept for compatibility.

The module contains exact and regex-based translations for common converter issues, including:

- missing/invalid Wix fields,
- duplicate handles,
- duplicate SKUs,
- merge conflicts,
- invalid decimal or quantity values,
- unresolved image references,
- unsupported image types,
- unconfigured uploads,
- Wix upload failures.

### `src/zeitshop_converter/io/media_migration.py`

Resolves local/remote product images and optionally uploads local files to Wix.

Important components:

- `WixUploadConnectivityError`
- `ensure_wix_upload_connectivity()`
- `ImageLibrary`
- `WixMediaClient`
- `attach_media_rows(...)`

Notable helper behavior:

- image reference splitting supports semicolon, newline, and pipe separators,
- local image paths are deduplicated by resolved path,
- URL strings are deduplicated case-insensitively,
- unresolved explicit image references become warnings,
- found local images without Wix credentials become warnings,
- Wix upload failures become warnings except connectivity failures, which are raised early.

`attach_media_rows` mutates the passed `ConversionBatch` in place by adding issues and media rows to each `WixRowResult`.

### `src/zeitshop_converter/io/xlsx_images.py`

Extracts embedded images from XLSX files.

Functions:

- `default_xlsx_image_export_dir(path)`
- `resolve_xlsx_image_export_dir(path, output_dir=None)`
- `default_xlsx_image_mapping_path(path, output_dir=None)`
- `write_image_mapping_csv(path, records)`
- `extract_xlsx_row_images(...)`

The extractor reads XLSX internals using `zipfile` and XML parsing, resolves drawing relationships, copies image binaries, and maps them to source row numbers.

### `src/zeitshop_converter/gui/__init__.py`

Small GUI export module.

Exports:

- `run_gui`

### `src/zeitshop_converter/gui/app.py`

Full Tkinter desktop application.

Important elements:

- optional `sv_ttk` theme loading,
- persisted settings via `GuiSettings`,
- `ConverterApp`, the main `tk.Tk` window,
- file selection and conversion execution,
- threaded conversion worker,
- queue-based worker-to-UI communication,
- summary counters and issue links,
- preview table rendering,
- search and sorting,
- inline cell editing,
- export row building and revalidation,
- Wix upload connectivity preflight,
- output file dialogs.

The GUI imports the same conversion and IO layer as the CLI rather than duplicating conversion logic.

## Scripts

### `scripts/launch_gui.py`

Tiny script used by PyInstaller. It imports `zeitshop_converter.main.main` and runs:

```python
main(["gui"])
```

This guarantees the packaged app starts the GUI directly.

### `scripts/build_windows.ps1`

PowerShell build script for a Windows desktop bundle.

It:

1. creates or reuses `.venv-windows-build`,
2. installs the package with GUI and Windows build extras,
3. removes old build artifacts,
4. runs PyInstaller in `--onedir` and `--windowed` mode,
5. collects `sv_ttk`,
6. zips `dist/ZeitshopConverter` into `dist/ZeitshopConverter-windows.zip`.

### `scripts/build_windows.cmd`

Small `cmd.exe` wrapper that runs the PowerShell script with execution policy bypass.

## Tests

The test suite is broad and organized by module behavior.

### `tests/test_normalize.py`

Covers:

- Swiss decimal formats,
- invalid decimal values,
- text normalization,
- decimal formatting,
- numeric inventory,
- stock enum inventory,
- fractional quantity rejection,
- handle generation.

### `tests/test_models.py`

Covers:

- `WixRowResult.has_errors`,
- `WixRowResult.has_warnings`,
- `ConversionBatch` filtering,
- valid row/media row aggregation,
- error and warning counts.

### `tests/test_pipeline.py`

Covers the core conversion pipeline:

- valid and invalid row mapping,
- duplicate article merging,
- quantity aggregation,
- name deduplication,
- reference-to-barcode behavior,
- duplicate barcode rewriting,
- merge-blocking field conflicts,
- equivalent decimal values during merge,
- invalid quantity merge behavior,
- avoiding duplicate numeric error messages.

### `tests/test_validation.py`

Covers:

- valid row acceptance,
- validation errors for core Wix fields,
- length warnings,
- cost precision boundaries.

### `tests/test_reader.py`

Covers:

- CSV canonicalization,
- image column preservation,
- empty column dropping,
- XLSX header detection after preamble rows,
- extension dispatch,
- empty CSV handling,
- repeated header row skipping,
- unsupported extension rejection,
- scalar cell formatting,
- XLSX reader fallback without `openpyxl`.

### `tests/test_detect.py`

Covers:

- optional `charset-normalizer` loading,
- encoding preference order,
- fallback encoding behavior,
- CSV dialect sniffing,
- semicolon fallback.

### `tests/test_template.py`

Covers:

- built-in template availability,
- required template columns,
- BOM/whitespace cleanup,
- empty template rejection.

### `tests/test_wix_writer.py`

Covers:

- output parent directory creation,
- header order preservation.

### `tests/test_error_writer.py`

Covers:

- German message translations,
- writing issue CSV rows,
- `write_error_csv` alias behavior.

### `tests/test_media_migration.py`

Covers:

- media rows from explicit URLs,
- local image matching by article number,
- missing explicit image warnings,
- helper normalization and deduplication,
- image library lookup modes,
- image root building,
- explicit path resolution,
- unsupported image warnings,
- upload failure warnings,
- connectivity errors,
- progress messages,
- required `media` column enforcement,
- Wix upload cache behavior,
- upload URL/file ID/media URL extraction,
- Wix request retry behavior,
- binary upload response and error handling.

### `tests/test_xlsx_images.py`

Covers:

- embedded XLSX image extraction,
- duplicate embedded file reuse,
- `export-images` mapping CSV output.

### `tests/test_conversion.py`

Covers:

- orchestration from reader to template loader to pipeline,
- media row attachment when enabled,
- image mapping file writing when embedded image export is enabled.

### `tests/test_main.py`

Covers:

- CLI parser defaults,
- default GUI dispatch,
- `gui` subcommand dispatch,
- `convert` subcommand dispatch,
- environment-sourced Wix credentials,
- warning-only issue report output,
- skipping issue writer when no issue output path is provided.

### `tests/test_gui_helpers.py`

Covers GUI logic that can be tested without full manual UI interaction:

- optional theme loading,
- settings load/save,
- environment credentials in GUI options,
- default download filename/path helpers,
- progress parsing,
- search matching,
- sort keys,
- preview override behavior,
- export row validation,
- barcode rewriting after edits,
- conversion error handling,
- offline upload preflight,
- summary metric updates,
- issue report opening,
- `run_gui` startup.

### `tests/_xlsx_factory.py`

Helper module for constructing XLSX test fixtures, including workbooks with embedded image relationships.

## Error Handling Style

The code uses two patterns:

1. Expected row-level data problems become `ValidationIssue` objects.
2. Workflow-level problems raise exceptions.

Examples of row-level issues:

- invalid price,
- invalid quantity,
- duplicate SKU,
- unresolved image reference,
- local image found but not uploadable.

Examples of raised workflow errors:

- unsupported DIAMOND file extension,
- invalid custom template,
- `export-images` used on a non-XLSX input,
- image migration requested with a template missing `media`,
- Wix upload connectivity failure in GUI preflight.

This split lets conversion continue for bad product rows while still stopping for invalid setup or impossible workflow states.

## Important Defaults

CLI defaults:

- GUI starts when no command is given.
- `visible=FALSE` unless `--default-visible` is passed.
- inventory mode is numeric.
- handle prefix is `ds-`.
- Wix image path is `/zeitshop`.

GUI defaults:

- `visible=TRUE`.
- handle prefix is `ds-`.
- output directory defaults to the input file directory.
- image migration is disabled.
- Wix image path is `/zeitshop`.

These defaults intentionally differ: the GUI is oriented around a shop-operator workflow, while the CLI keeps visibility conservative unless explicitly enabled.

## Local Files Written Outside The Repo

The converter may write user cache/settings data under:

```text
~/.zeitshop_converter/
```

Known files/directories:

- `gui_settings.json`: persisted GUI settings.
- `wix_media_cache.json`: local-file to Wix-media URL cache.
- `xlsx_images/...`: default extracted XLSX image cache.

Normal output files are written wherever the user chooses through CLI arguments or GUI save dialogs.

## Design Observations

The project is structured with a clean separation between:

- entrypoints (`main.py`, GUI),
- orchestration (`conversion.py`),
- pure conversion logic (`core/`),
- file/network boundaries (`io/`),
- packaging/build scripts (`scripts/`).

Most business rules are testable without a GUI or network. Network upload behavior is wrapped in `WixMediaClient` and tested through monkeypatching rather than real Wix calls.

The core conversion pipeline is intentionally deterministic:

- duplicate handling is stable,
- generated handles are stable,
- barcode fallback is stable,
- image references are deduplicated while preserving order,
- issue reports retain source row numbers.

This is important for a product import workflow because users need to understand exactly which source rows produced which Wix rows and which problems require correction.

## Typical Developer Commands

Install locally:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[gui,dev]
```

Run tests:

```bash
pytest -q
```

Run GUI:

```bash
python -m zeitshop_converter.main gui
```

Run conversion:

```bash
python -m zeitshop_converter.main convert \
  --diamond input.xlsx \
  --output out/wix_import.csv \
  --issues-output out/issues.csv
```

Extract embedded XLSX images:

```bash
python -m zeitshop_converter.main export-images \
  --diamond input.xlsx \
  --output-dir out/extracted_images \
  --mapping-output out/image_mapping.csv
```

Build Windows desktop package:

```powershell
./scripts/build_windows.ps1
```

