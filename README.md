# Zeitshop Converter

This project is a local Python application that converts product exports from DIAMOND SEVEN (CSV or XLSX) into a Wix-compatible import CSV. The codebase is designed so that the conversion logic is independent from the graphical interface, which means the same conversion engine can be run from a desktop window or from the command line, and it can also be tested automatically. The target audience is a small business workflow where someone exports inventory data, runs the converter, and then imports the generated file into Wix.

The application is intentionally simple at this stage and should be understood as an alpha version. Alpha here means the most important path works end-to-end, but some advanced business rules can still be added later as real usage reveals edge cases. Even in this early stage, the architecture is already structured in a clean way so future changes stay manageable.

## What this project does in practical terms

When you run a conversion, the program reads the DIAMOND file in a tolerant way. For CSV inputs, the reader handles unknown text encodings and varying delimiters. For XLSX inputs, it auto-detects the header row even when reports include preamble rows and image columns. In both cases, it removes empty placeholder columns and normalizes incoming columns into one canonical internal schema. After reading, the core pipeline transforms each logical product into the Wix format, applies validation rules for Wix-critical fields, and writes a final output CSV with exactly the same column order as the Wix template header.

A crucial detail in this project is that duplicate product rows in DIAMOND exports are merged by product identity before writing Wix rows. This matters for data like Maurice Lacroix where the same article appears in multiple branches. The merge step combines them into one unique product row and sums quantities, which avoids import conflicts caused by repeated products.

## Detailed conversion process from DIAMOND export to Wix CSV

The conversion pipeline is deterministic and happens in clearly separated phases. The first phase is raw file ingestion. For CSV files, the converter reads bytes and detects text encoding in a defensive order. It first tries UTF-8 variants, then Windows-style codepages such as cp1252, and finally falls back to a permissive decoder if needed. This approach is necessary because Windows export tools often produce files that look like text but are not UTF-8, and decoding incorrectly at this step can silently corrupt product names or price strings. For XLSX files, the converter reads the first worksheet and detects the most likely header row by matching canonical DIAMOND column names.

After decoding, the second phase is delimiter and structure detection. DIAMOND exports are often semicolon-delimited, but this is not guaranteed, so the converter uses CSV dialect sniffing to infer separators. It then reads the header row and removes structural noise such as empty header columns and optional media helper columns like `Bild` that are irrelevant for the current Wix import mode. At this point, the converter maps incoming header labels into one canonical internal schema so downstream logic can assume consistent keys like `Artikel Nr`, `Menge`, `Einstand`, and `Verkauf`.

The third phase is row filtering and canonical record creation. Completely empty lines are discarded, and footer-like summary rows are ignored if they do not contain product identity signals. Every remaining row becomes a `DiamondRecord` object with the original source line number attached, which is very important for debugging and for writing actionable error messages later.

The fourth phase is duplicate consolidation. The pipeline computes a product identity key using `Artikel Nr` first and `Referenz` as fallback. If multiple rows share that identity, they are merged into one logical product. During merge, quantity values are parsed and summed, while missing descriptive fields can be filled from sibling rows in the same group. This is the key mechanism that turns branch-split inventory rows into one Wix product row and prevents repeated product conflicts.

The fifth phase is field mapping into Wix shape. For each merged logical record, the mapper creates a dictionary initialized with the exact template header columns so output ordering is stable. It then sets essential Wix fields. `fieldType` is set to `PRODUCT`, `handle` is generated from product identity and deduplicated if needed, `name` is built from brand and description parts with a hard 80-character cap, `visible` is filled from conversion options, and `sku` is copied from DIAMOND identity fields.

The sixth phase is numeric normalization and inventory conversion. Price and cost strings from DIAMOND are normalized using decimal-safe parsing rules that remove Swiss thousand separators and harmonize comma versus dot decimal notation. This avoids floating-point errors and produces Wix-friendly numeric text values such as `3550.00`. Inventory is normalized either to numeric quantity or stock-status enums depending on user options. If parsing fails for a row, that failure is converted into a structured issue rather than crashing the whole conversion.

The seventh phase is validation against Wix-oriented constraints. The validator checks required fields and format constraints for important columns such as `fieldType`, `name`, `visible`, `price`, `inventory`, and `cost`. Validation outputs typed issues with severity (`ERROR` or `WARNING`), field name, source row, and human-readable message. This design allows the GUI and CLI to show the same diagnostics in a consistent format.

The eighth phase is batch assembly and export selection. All row results are collected into a `ConversionBatch`. Rows without blocking errors are considered valid export rows and are written to the Wix output CSV. Rows with blocking errors can be written to a separate error CSV including source values and issue details. The final writer always uses the template header order to ensure output shape matches the Wix import contract.

From a beginner perspective, the most important idea is that conversion is not one big function. It is a sequence of small, predictable transformations where each phase has one responsibility. This is why the system is easier to test, easier to debug, and safer to evolve when new edge cases appear in real DIAMOND exports.

## How the code is organized

The package lives in `src/zeitshop_converter` and follows a layered design. The `core` package contains pure business logic and knows nothing about windows, buttons, or file dialogs. The `io` package handles reading and writing files. The `gui` package contains Tkinter desktop code and acts as a shell around the core engine. The `main.py` module wires command-line entry points and the GUI launch mode. The `conversion.py` module is a small high-level service function that joins file reading and core conversion into one callable operation.

The easiest way to understand the control and data flow is to picture this path: input file selection happens in the GUI or CLI, file bytes are read in `io`, records are normalized and converted in `core`, validation is attached to each output row, and final CSV files are written again by `io`. The GUI never performs mapping rules itself. It only requests conversion, displays status, and triggers export commands.

## End-to-end flow from a beginner perspective

If you start from the GUI, the application window asks for a DIAMOND CSV or XLSX file. The Wix template header is baked into the application, so you do not need to select a template file each time. Once you click convert, the GUI passes the selected options into `convert_diamond_file`. That function reads raw DIAMOND records through `read_diamond_file`, loads the built-in template header through `load_template_header`, and calls `convert_records` to transform data. The result object contains all converted rows plus per-row issues.

After conversion, the GUI paints a preview table and marks row status as OK, WARNING, or ERROR depending on validation. If you click export, the GUI calls `write_wix_csv` to save valid rows and optionally `write_error_csv` to save problematic rows with explanations. The CLI path does the same operations, just without a desktop window.

## File-by-file documentation

### `pyproject.toml`

This file is the project configuration for packaging, dependencies, and tooling. It declares the package name, Python version requirement, and dependencies such as `charset-normalizer` and optional development dependencies like `pytest`. It also defines a console script entry point named `zeitshop-converter` that points to `zeitshop_converter.main:main`. For a beginner, this file is the “project manifest” that tells Python tools how to install and run the application.

The same file also configures setuptools to use `src/` layout and configures pytest so tests can import modules from `src`. This avoids path issues during development.

### `README.md`

This file is the document you are reading now. Its purpose is to explain what the project is, how it works, and how to run it safely. In production projects, this is usually the first file a new developer reads.

### `converter-report.md`

This is a research and planning document that captures design ideas, tradeoffs, and implementation guidance for the converter. It is not executed by Python and does not affect runtime behavior. It is useful context for why architecture choices were made.

### `Thomas Sabo.CSV`

This is a sample DIAMOND export used for testing real conversion behavior. It provides many rows with realistic field combinations and serves as a practical integration test input.

### `Maurice Lacroix Uhren.CSV`

This is a second sample DIAMOND export. It is especially important because it includes repeated product articles from different branches, which is exactly the type of input that required duplicate merge logic.

### `Wix_Templates_Products_Without_Categories_CSV.csv`

This file is the schema contract for output. The converter reads its header and writes output with exactly that column order. This avoids accidental column mismatch when importing into Wix.

### `out/wix_import_thomas_sabo.csv`

This is a generated output file produced by the converter for the Thomas Sabo sample. It is ready to be imported into Wix as long as the business content is accepted by Wix account rules.

### `out/wix_import_maurice_lacroix.csv`

This is a generated output file for the Maurice Lacroix sample after duplicate-merge logic is applied. It contains unique product rows and aggregated quantity where duplicates existed.

### `out/error_thomas_sabo.csv`

This is a generated error file. For the latest conversion run it only contains a header because there were no error rows.

### `out/error_maurice_lacroix.csv`

This is the generated error file for Maurice conversion and currently contains only a header as well, because the latest run had no conversion errors.

### `src/zeitshop_converter/__init__.py`

This module marks the package root and exposes package-level symbols. It defines `__version__` and re-exports `convert_diamond_file` so users can import a high-level API directly from the package. The import here is simple and serves convenience.

### `src/zeitshop_converter/conversion.py`

This module provides one high-level function named `convert_diamond_file`. The function accepts input file paths plus options, reads DIAMOND records through `io.read_diamond_file`, loads Wix headers through `io.load_template_header`, and delegates conversion to `core.convert_records`.

This file is intentionally small because it acts as the seam between file-level I/O and pure transformation logic. Its simplicity is a design strength because orchestration is easy to understand and test.

### `src/zeitshop_converter/main.py`

This module is the runtime entry point for both CLI and GUI usage. It imports `argparse` for command-line parsing, then defines `main`, `_build_parser`, and `_run_convert`. The parser supports a `gui` mode and a `convert` mode.

In `convert` mode, command-line options become a `ConversionOptions` object, then conversion is executed, then output files are written. In `gui` mode, it launches the Tkinter app. For beginners, this file is where “how the program starts” is defined.

### `src/zeitshop_converter/core/__init__.py`

This module re-exports core dataclasses and functions such as `ConversionBatch`, `ConversionOptions`, and `convert_records`. Re-exporting creates a cleaner import surface so other modules can import from `zeitshop_converter.core` without knowing every internal file path.

### `src/zeitshop_converter/core/models.py`

This file defines dataclasses and enums that represent the domain model. The `Severity` enum expresses warning versus error. `ValidationIssue` describes a single issue with source row, field, severity, and message. `DiamondRecord` wraps canonical input data and remembers source row number.

`ConversionOptions` stores behavioral switches like default visibility and inventory mode. `WixRowResult` stores one converted Wix row plus its issues and helper properties like `has_errors`. `ConversionBatch` stores all results and provides convenience properties such as valid rows and error rows. These classes are the central language that all layers use to communicate clearly.

### `src/zeitshop_converter/core/normalize.py`

This file implements foundational normalization helpers. The imports here include `Decimal` from `decimal` for reliable numeric handling and `re` for controlled text cleanup. `normalize_text` trims and compresses whitespace. `parse_decimal` supports Swiss-style number formats by removing thousands separators and normalizing decimal marks.

`format_decimal` writes decimals in a fixed format suitable for CSV output. `parse_quantity` parses quantity text into integer-like values. `normalize_inventory` converts raw quantity into either numeric inventory or stock-status enums depending on options. `make_handle` turns free text into a URL-safe handle.

For a beginner, this file is where “dirty input becomes consistent values” is implemented.

### `src/zeitshop_converter/core/mapping.py`

This module turns one canonical DIAMOND record into one Wix row dictionary. It imports normalization helpers and model types. The key function is `map_diamond_to_wix_row`, which creates a row containing only template columns and fills important Wix fields.

The module also contains helper functions for name construction, optional plain description composition, and handle de-duplication. It catches parse errors for price, cost, and inventory and converts them into structured `ValidationIssue` objects rather than crashing. This makes the converter robust and user-facing.

### `src/zeitshop_converter/core/validation.py`

This module applies Wix-oriented rule checks after mapping. It validates fields like `fieldType`, `name`, `visible`, `price`, `inventory`, and constraints on `cost`, `sku`, and `brand`. It imports `Decimal` and regex utilities so numeric checks are explicit and predictable.

The main function is `validate_wix_row`, which returns a list of issues. Errors indicate blocking problems, while warnings indicate potentially risky but still processable values. Keeping validation separate from mapping helps readability and maintainability.

### `src/zeitshop_converter/core/pipeline.py`

This module orchestrates conversion of many records and contains important preprocessing. It imports `Counter` and uses helper functions `_record_identity` and `_merge_records_by_identity` to group repeated products, merge fields, and sum quantities.

The main function `convert_records` applies mapping and validation for each merged record, tracks seen handles and SKUs, and returns a `ConversionBatch`. This file is the heart of the data flow because it defines how raw records become final conversion results.

### `src/zeitshop_converter/io/__init__.py`

This module re-exports file-layer functions so other parts of the app can import I/O helpers from one place. It keeps top-level imports in GUI and CLI code clean and simple.

### `src/zeitshop_converter/io/detect.py`

This module contains encoding and CSV dialect detection logic. It imports the standard `csv` module and optionally `charset_normalizer.from_bytes`. `detect_encoding` tries common encodings first and falls back to `charset-normalizer`, then to `latin1` as a safe last resort.

`sniff_dialect` uses `csv.Sniffer` with likely delimiters to infer whether the file is semicolon, comma, or tab separated. This logic is very important for Windows exports where file format style can vary.

### `src/zeitshop_converter/io/diamond_reader.py`

This module reads DIAMOND files into canonical `DiamondRecord` objects. It imports `csv`, `StringIO`, `Path`, normalization helpers, and detect helpers. It defines canonical column names and alias mapping so minor header variations are normalized.

The key reader functions are `read_diamond_csv`, `read_diamond_xlsx`, and the dispatch helper `read_diamond_file`. They normalize CSV and XLSX exports to the same canonical row shape, skip empty/footer summary rows, and return structured records with source row positions. This gives the core layer predictable input.

### `src/zeitshop_converter/io/wix_template.py`

This module loads and validates the Wix template header. It ensures the file is readable and checks required columns such as `handle`, `fieldType`, `name`, `visible`, `price`, `inventory`, and `sku`. If mandatory columns are missing, it raises a clear error.

This early validation protects users from silently generating incorrect output when the wrong template file is selected.

### `src/zeitshop_converter/io/wix_writer.py`

This module writes final Wix rows to disk. It uses `csv.DictWriter` with the exact template header order and ignores unknown fields. The function `write_wix_csv` creates parent directories if needed, writes UTF-8 CSV with a header row, and returns the number of written rows.

For beginners, this is where in-memory conversion results become a physical file that Wix can import.

### `src/zeitshop_converter/io/error_writer.py`

This module writes an error CSV containing source data and issue descriptions. It dynamically collects source column names from error rows, adds `error_codes` and `error_messages`, and writes a report file for manual correction workflows.

Even when there are no errors, the file can still be generated with just headers, which is useful as a consistent artifact.

### `src/zeitshop_converter/gui/__init__.py`

This module re-exports the `run_gui` function from `gui.app`. It keeps the GUI launch import straightforward for `main.py`.

### `src/zeitshop_converter/gui/app.py`

This is the Tkinter desktop application. It imports `tkinter`, themed `ttk` widgets, file dialogs, and message boxes. It also imports conversion and writer functions from non-GUI layers. The class `ConverterApp` builds the window, stores user selections in Tk variables, and defines button handlers.

The method `_run_conversion` gathers options and triggers core conversion. The method `_render_preview` displays row status in a table with color tags. The export handlers call writer functions to produce output files. Because this file only orchestrates behavior and presentation, business rules remain testable in core modules.

### `tests/test_normalize.py`

This test module verifies number parsing, inventory normalization, and handle generation from `core.normalize`. It ensures Swiss numeric formats and invalid inputs are handled as expected. These tests protect low-level correctness because many higher-level features depend on this behavior.

### `tests/test_reader.py`

This module tests DIAMOND reading behavior, especially dropping `Bild` and empty columns and preserving expected canonical values. It creates a temporary CSV file and asserts parsed record content. This ensures the reader remains tolerant to real export quirks.

### `tests/test_pipeline.py`

This module tests conversion orchestration at record level. It validates that good rows stay valid, bad rows become errors, and duplicate article rows are merged with summed inventory. This is important because pipeline behavior directly affects what gets exported to Wix.

### `tests/test_template.py`

This test verifies that template validation fails when required columns are missing. It prevents regressions where incorrect template files would pass silently.

## Control flow and data flow together

The runtime starts in `main.py`. If the user chooses GUI mode, `run_gui` builds a window and waits for actions. When conversion is requested, GUI code calls `convert_diamond_file`. If the user chooses CLI mode, `main.py` parses arguments and calls the same conversion function. In both paths, the actual conversion path is identical.

Inside `convert_diamond_file`, DIAMOND input is parsed by `read_diamond_file` and template schema is loaded by `load_template_header`. Then `convert_records` performs merge, mapping, and validation. A `ConversionBatch` returns all results plus convenience subsets. Writers serialize either valid rows or error rows to disk. This shared path guarantees that GUI and CLI produce consistent data.

## How this relates to Windows app development for beginners

Even though the program is written in Python and runs cross-platform, the GUI architecture is exactly the style used in many simple Windows desktop tools. The user interacts through a local window, chooses local files, and saves local output. There is no server and no cloud dependency in this flow.

Tkinter is included with Python and is often the easiest entry point to desktop development for beginners. In this project, Tkinter is only a presentation layer. The business logic is in plain Python modules, which is a good professional practice because it keeps desktop code maintainable and testable.

## How to run and verify safely

Create a virtual environment and install dependencies with editable mode so code changes are immediately reflected. Run tests first to verify baseline correctness. Then run conversion commands for each sample CSV and inspect `out/` files. If a conversion fails, the error message and any generated error CSV usually point to the exact field and row that needs attention.

Use these commands exactly as written.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
PYTHONPATH=src python -m zeitshop_converter.main convert --diamond "Thomas Sabo.CSV" --output out/wix_import_thomas_sabo.csv --error-output out/error_thomas_sabo.csv
PYTHONPATH=src python -m zeitshop_converter.main convert --diamond "Maurice Lacroix Uhren.CSV" --output out/wix_import_maurice_lacroix.csv --error-output out/error_maurice_lacroix.csv
PYTHONPATH=src python -m zeitshop_converter.main gui
```

## Quick Linux test workflow (CLI and GUI)

Even though distribution will later target Windows, you can develop and test everything on Linux first. The converter logic and CLI run the same way on Linux. For GUI tests, Tkinter must be available in your Python installation. On Debian or Ubuntu based systems, install it with `sudo apt install python3-tk` if the GUI does not start.

For CLI testing on Linux, create and activate a virtual environment, install dependencies, and run conversion directly with the built-in template.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
PYTHONPATH=src python -m zeitshop_converter.main convert --diamond "Thomas Sabo.CSV" --output out/wix_import_thomas_sabo.csv --error-output out/error_thomas_sabo.csv
```

For GUI testing on Linux, use the same environment and start the GUI entrypoint. You only need to select the DIAMOND CSV/XLSX export, because the Wix template header is now built into the app.

```bash
source .venv/bin/activate
PYTHONPATH=src python -m zeitshop_converter.main gui
```

## Final beginner summary

If you are new to app development, the most important idea in this project is separation of concerns. File reading logic lives in `io`, transformation rules live in `core`, and user interaction lives in `gui`. This architecture makes debugging easier, testing possible, and future features less risky. When you understand that one principle, the rest of the codebase becomes much easier to navigate.
