import csv
from pathlib import Path

from zeitshop_converter.io.wix_writer import write_wix_csv


def test_write_wix_csv_creates_parent_directory_and_preserves_header_order(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "wix.csv"
    header = ["handle", "name", "price"]
    rows = [
        {"name": "First", "handle": "one", "price": "10.00", "ignored": "x"},
        {"handle": "two", "name": "Second"},
    ]

    written = write_wix_csv(output, header, rows)

    assert written == 2
    assert output.exists()

    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == header
        parsed = list(reader)

    assert parsed == [
        {"handle": "one", "name": "First", "price": "10.00"},
        {"handle": "two", "name": "Second", "price": ""},
    ]

