import csv
from pathlib import Path

from tests._xlsx_factory import build_sample_diamond_xlsx
from zeitshop_converter.io.diamond_reader import read_diamond_xlsx
from zeitshop_converter.main import main


def test_reader_extracts_embedded_images_from_xlsx(tmp_path: Path) -> None:
    export_dir = tmp_path / "images"
    sample_path = build_sample_diamond_xlsx(tmp_path / "sample_embedded_images.xlsx")

    records = read_diamond_xlsx(
        sample_path,
        extract_embedded_images=True,
        image_export_dir=export_dir,
    )

    first = records[0]
    image_path = Path(first.data["Bild"])

    assert first.source_row == 11
    assert image_path.is_absolute()
    assert image_path.exists()
    assert image_path.parent == export_dir
    assert image_path.suffix.casefold() == ".png"


def test_reader_reuses_same_exported_file_for_duplicate_embedded_images(tmp_path: Path) -> None:
    export_dir = tmp_path / "images"
    sample_path = build_sample_diamond_xlsx(tmp_path / "sample_duplicate_images.xlsx")

    records = read_diamond_xlsx(
        sample_path,
        extract_embedded_images=True,
        image_export_dir=export_dir,
    )

    groups: dict[str, list[object]] = {}
    for record in records:
        image_ref = str(record.data.get("Bild", "")).strip()
        if not image_ref:
            continue
        groups.setdefault(image_ref, []).append(record)

    duplicate_group = next(group for group in groups.values() if len(group) > 1)

    assert [record.source_row for record in duplicate_group] == [20, 23]
    assert {record.data["Artikel Nr"] for record in duplicate_group} == {"SKU-2202"}


def test_export_images_command_writes_mapping_csv(tmp_path: Path) -> None:
    export_dir = tmp_path / "images"
    mapping_path = tmp_path / "mapping.csv"
    sample_path = build_sample_diamond_xlsx(tmp_path / "sample_embedded_images.xlsx")

    exit_code = main(
        [
            "export-images",
            "--diamond",
            str(sample_path),
            "--output-dir",
            str(export_dir),
            "--mapping-output",
            str(mapping_path),
        ]
    )

    assert exit_code == 0
    assert mapping_path.exists()

    with mapping_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert rows[0]["source_row"] == "11"
    assert rows[0]["artikel_nr"] == "SKU-1201"
    assert Path(rows[0]["bild"]).exists()
