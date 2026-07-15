from pathlib import Path

import pytest

from zeitshop_converter.io import diamond_reader
from zeitshop_converter.io.diamond_reader import read_diamond_csv, read_diamond_file
from zeitshop_converter.io.report_reader import ReportDescriptionRecord, read_report_description_csv


def test_reader_drops_empty_columns(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.csv"
    file_path.write_text(
        "Filiale;Kategorie;Warengruppe;Marke;;Produktlinie;Artikel Nr;Kurzbeschreibung;;Referenz;Menge;Einstand;;Verkauf\n"
        "Store-West;Category-A;Segment-B;Brand-X;;Linea;SKU-1001;Linea;;REF-1001;1;1'775.00;;3'550.00\n",
        encoding="cp1252",
    )

    records = read_diamond_csv(file_path)

    assert len(records) == 1
    row = records[0]
    assert row.source_row == 2
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


def test_reader_maps_columntextbox_export_by_position(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.csv"
    file_path.write_text(
        "ColumnTextBox1;ColumnTextBox2;ColumnTextBox3;ColumnTextBox4;ColumnTextBox5;ColumnTextBox6;ColumnTextBox7;ColumnTextBox8;ColumnTextBox9;ColumnTextBox10;ColumnTextBox11\n"
        "Am Bogen;Schmuck;Beads & Charms;Thomas Sabo;Charm Club;111819;Charm Flügel;0613-001-12;1;21.15;55.00\n",
        encoding="cp1252",
    )

    records = read_diamond_csv(file_path)

    assert len(records) == 1
    assert records[0].data["Filiale"] == "Am Bogen"
    assert records[0].data["Artikel Nr"] == "111819"
    assert records[0].data["Kurzbeschreibung"] == "Charm Flügel"
    assert records[0].data["Menge"] == "1"
    assert records[0].data["Verkauf"] == "55.00"


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


def test_reader_marks_lager_csv_source_format(tmp_path: Path) -> None:
    file_path = tmp_path / "lager.csv"
    file_path.write_text(
        "Bild;Filiale;Artikel Nr;Kategorie;Warengruppe;Marke;Produktlinie;Referenz;Serien Nr;Menge;Einstand;Verkauf;AURONOS;Status\n"
        ";Am Bogen;117759;Uhr;Herrenuhr;Maurice Lacroix;Aikon;AI6008-SS002-430-1;;1;1'025.00;2'050.00;0;Aktiv\n",
        encoding="cp1252",
    )

    records = read_diamond_csv(file_path)

    assert len(records) == 1
    assert records[0].source_format == "lager_csv"
    assert records[0].data["Kurzbeschreibung"] == ""


def test_read_report_description_csv_extracts_identity_and_description(tmp_path: Path) -> None:
    file_path = tmp_path / "report.csv"
    file_path.write_text(
        "Laden;;;;25.05.2026\n"
        ";Beschreibung;;Preis;\n"
        ";;;;\n"
        ";;Aikon Automatic;2'050.00;\n"
        ";;;;\n"
        ";;117759 | AI6008-SS002-430-1;;\n"
        ";;Edelstahlgehäuse und -band, blaues Zifferblatt;;\n",
        encoding="cp1252",
    )

    records = read_report_description_csv(file_path)

    assert records == [
        ReportDescriptionRecord(
            source_row=6,
            artikel_nr="117759",
            referenz="AI6008-SS002-430-1",
            beschreibung="Edelstahlgehäuse und -band, blaues Zifferblatt",
        )
    ]
