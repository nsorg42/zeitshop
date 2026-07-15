from pathlib import Path
from types import SimpleNamespace

from zeitshop_converter.conversion import convert_diamond_file
from zeitshop_converter.core.normalize import normalize_text, parse_quantity
from zeitshop_converter.gui.app import ConverterApp
from zeitshop_converter.inventory_update import build_inventory_update_batch
from zeitshop_converter.io import read_diamond_file, read_report_description_csv, write_wix_csv


TESTING_DATA = Path(__file__).resolve().parents[1] / "testing_data"
WATCH_BRANDS = [
    "Aerowatch",
    "Certina",
    "Edles und Rares",
    "Eichmüller",
    "Gingko",
    "Hamilton",
    "Hazuba",
    "ICE Watch",
    "Maurice Lacroix",
    "Rado",
    "SuperKids",
    "Thomas Sabo",
    "Tissot",
]
REQUIRED_WIX_PRODUCT_COLUMNS = {
    "fieldType",
    "name",
    "brand",
    "plainDescription",
    "inventory",
    "sku",
}
OLD_AVAILABILITY_MARKERS = ("Ladengeschäft", "Ladengeschäften")


def _article_key(value: str | None) -> str:
    text = normalize_text(value)
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _assert_import_batch_shape(batch) -> None:
    assert batch.results
    assert batch.valid_rows
    assert batch.error_count == 0

    for row in batch.valid_rows[:20]:
        assert REQUIRED_WIX_PRODUCT_COLUMNS.issubset(row)
        assert row["fieldType"] == "PRODUCT"
        assert row["sku"]
        assert row["brand"]
        assert row["inventory"].isdigit()

    descriptions = [row["plainDescription"] for row in batch.valid_rows]
    assert any("Verfügbar in der Bijouterie" in value for value in descriptions)
    assert all(
        marker not in value
        for value in descriptions
        for marker in OLD_AVAILABILITY_MARKERS
    )


def test_sample_sabo_import_and_report_description_files_are_readable() -> None:
    batch = convert_diamond_file(TESTING_DATA / "sabotab.csv")
    report_descriptions = read_report_description_csv(TESTING_DATA / "saboinf.csv")

    _assert_import_batch_shape(batch)
    assert report_descriptions

    for description in report_descriptions[:20]:
        assert description.artikel_nr
        assert description.beschreibung


def test_sample_watch_import_merges_rows_and_uses_new_availability_text() -> None:
    records = read_diamond_file(TESTING_DATA / "uhrtab.csv")
    batch = convert_diamond_file(TESTING_DATA / "uhrtab.csv")

    _assert_import_batch_shape(batch)
    by_sku = {row["sku"]: row for row in batch.valid_rows}
    expected_inventory: dict[str, int] = {}
    for record in records:
        article = _article_key(record.data.get("Artikel Nr"))
        if not article:
            continue
        expected_inventory[article] = expected_inventory.get(article, 0) + (
            parse_quantity(record.data.get("Menge")) or 0
        )

    assert len(by_sku) == len(expected_inventory)
    merged_skus = [sku for sku, quantity in expected_inventory.items() if quantity > 1]
    assert merged_skus
    for sku in merged_skus[:10]:
        assert by_sku[sku]["inventory"] == str(expected_inventory[sku])


def test_sample_update_round_trip_against_matching_wix_import(tmp_path: Path) -> None:
    batch = build_inventory_update_batch(
        wix_export_csv=TESTING_DATA / "uhrtab_wix_import.csv",
        diamond_csv=TESTING_DATA / "uhrtab.csv",
        brands=WATCH_BRANDS,
    )

    assert batch.has_blocking_errors is False
    assert batch.error_count == 0
    assert batch.rows
    assert batch.results
    assert batch.matched_count > 0

    first_existing_index = next(
        (
            index
            for index, result in enumerate(batch.results)
            if not result.is_new_product
        ),
        len(batch.results),
    )
    assert all(result.is_new_product for result in batch.results[:first_existing_index])
    assert all(not result.is_new_product for result in batch.results[first_existing_index:])

    output = tmp_path / "updated_wix.csv"
    assert write_wix_csv(output, batch.header, batch.rows) == len(batch.rows)
    written = output.read_text(encoding="utf-8")
    header = written.splitlines()[0]
    assert "sku" in header
    assert "inventory" in header
    assert "plainDescription" in header
    assert "Verfügbar in der Bijouterie" in written


def test_sample_update_report_descriptions_only_touch_new_rows() -> None:
    batch = build_inventory_update_batch(
        wix_export_csv=TESTING_DATA / "catalog_productswix.csv",
        diamond_csv=TESTING_DATA / "uhrtab.csv",
        brands=WATCH_BRANDS,
    )

    assert batch.has_blocking_errors is False
    assert batch.error_count == 0
    assert batch.rows
    assert batch.results

    new_results = [result for result in batch.results if result.is_new_product]
    assert batch.results[: len(new_results)] == new_results
    assert batch.new_product_count == len(new_results)

    original_existing_descriptions = {
        result.wix_row.get("sku", ""): result.wix_row.get("plainDescription", "")
        for result in batch.results
        if not result.is_new_product
    }

    fake_app = SimpleNamespace(update_batch=batch)
    matched = ConverterApp._apply_report_descriptions_to_new_update_rows(
        fake_app,
        read_report_description_csv(TESTING_DATA / "uhrinfo.csv"),
    )

    assert matched <= batch.new_product_count
    assert {
        result.wix_row.get("sku", ""): result.wix_row.get("plainDescription", "")
        for result in batch.results
        if not result.is_new_product
    } == original_existing_descriptions
    assert all(result.source_kind == "diamond" for result in new_results)


def test_windows_install_uninstall_and_reinstall_scripts_are_present() -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"

    assert (scripts / "install_windows.cmd").exists()
    assert (scripts / "install_windows.ps1").exists()
    assert (scripts / "uninstall_windows.cmd").exists()
    assert (scripts / "uninstall_windows.ps1").exists()
    assert (scripts / "reinstall_windows.cmd").exists()
    assert (scripts / "reinstall_windows.ps1").exists()

    reinstall_script = (scripts / "reinstall_windows.ps1").read_text(encoding="utf-8")
    assert "uninstall_windows.ps1" in reinstall_script
    assert "install_windows.ps1" in reinstall_script
    assert "-InstallDir" in reinstall_script
