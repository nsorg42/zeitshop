from pathlib import Path

import pytest

from zeitshop_converter.inventory_update import build_inventory_update_batch


def test_build_inventory_update_batch_updates_only_matching_product_inventory(tmp_path: Path) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Artikel Nr;Menge\n"
        "Am Bogen;A1;1\n"
        "Droz;A1;2\n"
        "Am Bogen;A2;0\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,inventory,sku\n"
        "one,PRODUCT,Alpha,9,A1\n"
        "two,PRODUCT,Beta,5,A2\n"
        "three,PRODUCT,Gamma,7,A3\n"
        "one,MEDIA,,,A1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(wix_export_csv=wix_csv, diamond_csv=diamond_csv)

    assert batch.header == ["handle", "fieldType", "name", "inventory", "sku"]
    assert len(batch.rows) == 4
    assert len(batch.results) == 3
    assert batch.matched_count == 2
    assert batch.changed_count == 2

    assert batch.rows[0]["inventory"] == "3"
    assert batch.rows[1]["inventory"] == "0"
    assert batch.rows[2]["inventory"] == "7"
    assert batch.rows[3]["inventory"] == ""

    assert batch.results[0].matched is True
    assert batch.results[0].changed is True
    assert batch.results[2].matched is False
    assert batch.results[2].changed is False


def test_build_inventory_update_batch_rejects_invalid_quantities(tmp_path: Path) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Artikel Nr;Menge\n"
        "Am Bogen;A1;oops\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,inventory,sku\n"
        "one,PRODUCT,Alpha,9,A1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Ungültige Menge"):
        build_inventory_update_batch(wix_export_csv=wix_csv, diamond_csv=diamond_csv)
