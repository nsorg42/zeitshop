from pathlib import Path

import pytest

from zeitshop_converter.io import diamond_reader
from zeitshop_converter.io.diamond_reader import read_diamond_csv, read_diamond_file


def test_reader_keeps_bild_and_drops_empty_columns(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.csv"
    file_path.write_text(
        "Bild;Filiale;Kategorie;Warengruppe;Marke;;Produktlinie;Artikel Nr;Kurzbeschreibung;;Referenz;Menge;Einstand;;Verkauf\n"
        "images/sku-1001.jpg;Store-West;Category-A;Segment-B;Brand-X;;Linea;SKU-1001;Linea;;REF-1001;1;1'775.00;;3'550.00\n",
        encoding="cp1252",
    )

    records = read_diamond_csv(file_path)

    assert len(records) == 1
    row = records[0]
    assert row.source_row == 2
    assert row.data["Bild"] == "images/sku-1001.jpg"
    assert row.data["Filiale"] == "Store-West"
    assert row.data["Artikel Nr"] == "SKU-1001"
    assert row.data["Verkauf"] == "3'550.00"


def test_reader_dispatches_csv_by_extension(tmp_path: Path) -> None:
    csv_path = tmp_path / "diamond.CSV"
    csv_path.write_text(
        "Filiale;Artikel Nr;Kurzbeschreibung;Menge;Einstand;Verkauf\n"
        "Store-West;10;Sample;1;5;9\n",
        encoding="utf-8",
    )

    records = read_diamond_file(csv_path)

    assert len(records) == 1
    assert records[0].data["Artikel Nr"] == "10"


def test_reader_csv_empty_file_returns_no_records(tmp_path: Path) -> None:
    file_path = tmp_path / "empty.csv"
    file_path.write_text("", encoding="utf-8")

    assert read_diamond_csv(file_path) == []


def test_reader_skips_repeated_header_rows_in_csv(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.csv"
    file_path.write_text(
        "Filiale;Artikel Nr;Kurzbeschreibung;Referenz;Menge;Einstand;Verkauf\n"
        "Filiale;Artikel Nr;Kurzbeschreibung;Referenz;Menge;Einstand;Verkauf\n"
        "Store-West;10;Sample;REF-10;1;5;9\n",
        encoding="utf-8",
    )

    records = read_diamond_csv(file_path)

    assert len(records) == 1
    assert records[0].source_row == 3
    assert records[0].data["Artikel Nr"] == "10"


def test_reader_rejects_unsupported_file_extension(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.xlsx"
    file_path.write_text("test", encoding="utf-8")

    with pytest.raises(ValueError, match="Please provide a .csv file"):
        read_diamond_file(file_path)


def test_reader_formats_scalar_cell_types() -> None:
    assert diamond_reader._cell_to_text(True) == "TRUE"
    assert diamond_reader._cell_to_text(2.5) == "2.5"
    assert diamond_reader._cell_to_text(3) == "3"
    assert diamond_reader._cell_to_text("  a  b  ") == "a b"
