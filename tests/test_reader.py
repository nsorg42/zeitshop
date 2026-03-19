from pathlib import Path

from zeitshop_converter.io.diamond_reader import read_diamond_csv


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
