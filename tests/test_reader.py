from pathlib import Path

import pytest
from openpyxl import Workbook

from zeitshop_converter.io import diamond_reader
from zeitshop_converter.io.diamond_reader import read_diamond_csv
from zeitshop_converter.io.diamond_reader import read_diamond_file
from zeitshop_converter.io.diamond_reader import read_diamond_xlsx


def test_reader_drops_bild_and_empty_columns(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.csv"
    file_path.write_text(
        "Bild;Filiale;Kategorie;Warengruppe;Marke;;Produktlinie;Artikel Nr;Kurzbeschreibung;;Referenz;Menge;Einstand;;Verkauf\n"
        ";Am Bogen;Uhr;Herrenuhr;Maurice;;Pontos;126523;Pontos;;PT6038;1;1'775.00;;3'550.00\n",
        encoding="cp1252",
    )

    records = read_diamond_csv(file_path)

    assert len(records) == 1
    row = records[0]
    assert row.source_row == 2
    assert row.data["Filiale"] == "Am Bogen"
    assert row.data["Artikel Nr"] == "126523"
    assert row.data["Verkauf"] == "3'550.00"
    assert "Bild" not in row.data


def test_reader_parses_xlsx_with_preamble_and_header_row(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.xlsx"

    workbook = Workbook()
    worksheet = workbook.active

    worksheet["A2"] = "Lager"
    worksheet["A7"] = "Kriterien:"
    worksheet["A9"] = "Bild"
    worksheet["E9"] = "Filiale"
    worksheet["F9"] = "Artikel Nr"
    worksheet["G9"] = "Kategorie"
    worksheet["H9"] = "Warengruppe"
    worksheet["J9"] = "Marke"
    worksheet["K9"] = "Produktlinie"
    worksheet["L9"] = "Referenz"
    worksheet["N9"] = "Kurzbeschreibung"
    worksheet["O9"] = "Menge"
    worksheet["P9"] = "Einstand"
    worksheet["Q9"] = "Verkauf"

    worksheet["E11"] = "Am Bogen"
    worksheet["F11"] = "126523"
    worksheet["G11"] = "Uhr"
    worksheet["H11"] = "Herrenuhr"
    worksheet["J11"] = "Maurice"
    worksheet["K11"] = "Pontos"
    worksheet["L11"] = "PT6038"
    worksheet["N11"] = "Pontos"
    worksheet["O11"] = 1
    worksheet["P11"] = "1'775.00"
    worksheet["Q11"] = "3'550.00"

    workbook.save(file_path)

    records = read_diamond_xlsx(file_path)

    assert len(records) == 1
    row = records[0]
    assert row.source_row == 11
    assert row.data["Filiale"] == "Am Bogen"
    assert row.data["Artikel Nr"] == "126523"
    assert row.data["Referenz"] == "PT6038"
    assert row.data["Menge"] == "1"
    assert row.data["Verkauf"] == "3'550.00"


def test_reader_dispatches_by_extension(tmp_path: Path) -> None:
    csv_path = tmp_path / "diamond.CSV"
    csv_path.write_text(
        "Filiale;Artikel Nr;Kurzbeschreibung;Menge;Einstand;Verkauf\n"
        "Am Bogen;10;Sample;1;5;9\n",
        encoding="utf-8",
    )

    csv_records = read_diamond_file(csv_path)
    assert len(csv_records) == 1
    assert csv_records[0].data["Artikel Nr"] == "10"

    xlsx_path = tmp_path / "diamond.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet["A1"] = "Artikel Nr"
    worksheet["B1"] = "Kurzbeschreibung"
    worksheet["C1"] = "Menge"
    worksheet["D1"] = "Einstand"
    worksheet["E1"] = "Verkauf"
    worksheet["A2"] = "11"
    worksheet["B2"] = "Sample X"
    worksheet["C2"] = "2"
    worksheet["D2"] = "7"
    worksheet["E2"] = "13"
    workbook.save(xlsx_path)

    xlsx_records = read_diamond_file(xlsx_path)
    assert len(xlsx_records) == 1
    assert xlsx_records[0].data["Artikel Nr"] == "11"


def test_reader_skips_repeated_header_rows_in_csv(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.csv"
    file_path.write_text(
        "Filiale;Artikel Nr;Kurzbeschreibung;Referenz;Menge;Einstand;Verkauf\n"
        "Filiale;Artikel Nr;Kurzbeschreibung;Referenz;Menge;Einstand;Verkauf\n"
        "Am Bogen;10;Sample;REF-10;1;5;9\n",
        encoding="utf-8",
    )

    records = read_diamond_csv(file_path)

    assert len(records) == 1
    assert records[0].source_row == 3
    assert records[0].data["Artikel Nr"] == "10"


def test_reader_skips_repeated_header_rows_in_xlsx(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Artikel Nr", "Kurzbeschreibung", "Referenz", "Menge", "Einstand", "Verkauf"])
    worksheet.append(["11", "Sample A", "REF-11", 1, "5", "9"])
    worksheet.append(["Artikel Nr", "Kurzbeschreibung", "Referenz", "Menge", "Einstand", "Verkauf"])
    worksheet.append(["12", "Sample B", "REF-12", 2, "6", "10"])
    workbook.save(file_path)

    records = read_diamond_xlsx(file_path)

    assert len(records) == 2
    assert records[0].source_row == 2
    assert records[0].data["Artikel Nr"] == "11"
    assert records[1].source_row == 4
    assert records[1].data["Artikel Nr"] == "12"


def test_reader_rejects_unsupported_file_extension(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.txt"
    file_path.write_text("test", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported DIAMOND format"):
        read_diamond_file(file_path)


def test_reader_xlsx_fallback_works_without_openpyxl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diamond_reader, "load_workbook", None)

    records = diamond_reader.read_diamond_xlsx(Path("testing_data/radoxlsx.xlsx"))

    assert records
    assert records[0].source_row == 11
    assert records[0].data["Artikel Nr"] == "120659"
