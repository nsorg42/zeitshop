# CLI testing on Linux
- create and activate a virtual environment
- install dependencies
- run conversion directly with the built-in template.


python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
PYTHONPATH=src python -m zeitshop_converter.main convert --diamond "Thomas Sabo.CSV" --output out/wix_import_thomas_sabo.csv --error-output out/error_thomas_sabo.csv


# GUI testing

source .venv/bin/activate
PYTHONPATH=src python -m zeitshop_converter.main gui

# Cleanup

deactivate


