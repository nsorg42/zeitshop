# zeitshop-converter (alpha skeleton)

Alpha implementation of a local DIAMOND CSV -> Wix CSV converter with a strict separation between:

- conversion logic (`core/` + `io/`) for testing and CLI usage
- GUI orchestration (`gui/`) for interactive workflow

## Repository structure

```text
src/zeitshop_converter/
  core/
    models.py
    normalize.py
    mapping.py
    validation.py
    pipeline.py
  io/
    detect.py
    diamond_reader.py
    wix_template.py
    wix_writer.py
    error_writer.py
  gui/
    app.py
  conversion.py
  main.py
tests/
  test_normalize.py
  test_reader.py
  test_pipeline.py
```

## Run tests

```bash
pytest
```

## Run CLI conversion

```bash
python -m zeitshop_converter.main convert \
  --diamond "Thomas Sabo.CSV" \
  --template "Wix_Templates_Products_Without_Categories_CSV.csv" \
  --output out/wix_import.csv \
  --error-output out/error_rows.csv
```

## Run GUI

```bash
python -m zeitshop_converter.main gui
```
