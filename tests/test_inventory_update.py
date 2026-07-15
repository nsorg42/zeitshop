from pathlib import Path

import pytest

from zeitshop_converter.inventory_update import build_inventory_update_batch


def test_build_inventory_update_batch_updates_only_matching_product_inventory(tmp_path: Path) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;A1;1\n"
        "Droz;Brand;A1;2\n"
        "Am Bogen;Brand;A2;0\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,9,A1\n"
        "two,PRODUCT,Beta,Brand,5,A2\n"
        "three,PRODUCT,Gamma,Brand,7,A3\n"
        "one,MEDIA,,,,A1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.header == ["handle", "fieldType", "name", "brand", "inventory", "sku"]
    assert len(batch.rows) == 4
    assert len(batch.results) == 3
    assert batch.matched_count == 2
    assert batch.changed_count == 3
    assert batch.set_to_zero_count == 1
    assert batch.has_blocking_errors is False

    assert batch.rows[0]["inventory"] == "3"
    assert batch.rows[1]["inventory"] == "0"
    assert batch.rows[2]["inventory"] == "0"
    assert batch.rows[3]["inventory"] == ""

    assert batch.results[0].matched is True
    assert batch.results[0].changed is True
    assert batch.results[2].matched is False
    assert batch.results[2].changed is True
    assert batch.results[2].set_to_zero is True


def test_build_inventory_update_batch_rejects_invalid_quantities(tmp_path: Path) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;A1;oops\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,9,A1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Ungültige Menge"):
        build_inventory_update_batch(
            wix_export_csv=wix_csv,
            diamond_csv=diamond_csv,
            brands=["Brand"],
        )


def test_build_inventory_update_batch_updates_inventory_and_availability_descriptions(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Droz;Brand;A1;2\n"
        "Am Bogen;Brand;A2;1\n"
        "Droz;Brand;A2;1\n"
        "Am Bogen;Brand;A3;0\n"
        "Am Bogen;Brand;A4;1\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,plainDescription,inventory,sku\n"
        'one,PRODUCT,Alpha,Brand,"Specs A1\nVerfügbar in dem Ladengeschäft Bijouterie Am Bogen in Bremgarten AG",9,A1\n'
        'two,PRODUCT,Beta,Brand,"Specs A2 | Verfügbar in dem Ladengeschäft Bijouterie Droz in Zofingen AG",5,A2\n'
        'three,PRODUCT,Gamma,Brand,"Specs A3\nVerfügbar in den Ladengeschäften Bijouterie Am Bogen in Bremgarten AG und in der Bijouterie Droz in Zofingen AG",7,A3\n'
        "four,PRODUCT,Delta,Brand,Specs A4,1,A4\n"
        'five,PRODUCT,Epsilon,Brand,"Specs A5 | VERFÜGBAR IN DER BIJOUTERIE AM BOGEN IN BREMGARTEN AG",2,A5\n',
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.changed_count == 5
    assert batch.rows[0]["plainDescription"] == (
        "Specs A1\nVerfügbar in der Bijouterie Droz in Zofingen AG"
    )
    assert batch.rows[1]["plainDescription"] == (
        "Specs A2\nVerfügbar in der Bijouterie am Bogen in Bremgarten AG "
        "und in der Bijouterie Droz in Zofingen AG"
    )
    assert batch.rows[2]["plainDescription"] == "Specs A3"
    assert batch.rows[3]["plainDescription"] == (
        "Specs A4\nVerfügbar in der Bijouterie am Bogen in Bremgarten AG"
    )
    assert batch.rows[4]["plainDescription"] == "Specs A5"

    assert batch.results[0].changed is True
    assert batch.results[1].changed is True
    assert batch.results[2].changed is True
    assert batch.results[3].changed is True
    assert batch.results[4].changed is True


def test_build_inventory_update_batch_updates_html_availability_descriptions(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Droz;Brand;A1;2\n"
        "Am Bogen;Brand;A2;0\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,plainDescription,inventory,sku\n"
        'one,PRODUCT,Alpha,Brand,"<p>Specs<br>Verfügbar in dem Ladengeschäft Bijouterie Am Bogen in Bremgarten AG</p>",2,A1\n'
        'two,PRODUCT,Beta,Brand,"<p>Specs<br />Verfügbar in dem Ladengeschäft Bijouterie Droz in Zofingen AG</p>",1,A2\n',
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.rows[0]["plainDescription"] == (
        "<p>Specs<br>Verfügbar in der Bijouterie Droz in Zofingen AG</p>"
    )
    assert batch.rows[0]["plainDescription"].count("Verfügbar") == 1
    assert batch.rows[1]["plainDescription"] == "<p>Specs</p>"
    assert batch.rows[1]["plainDescription"].count("Verfügbar") == 0


def test_build_inventory_update_batch_reads_semicolon_wix_export(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;A1;1\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle;fieldType;name;brand;inventory;sku\n"
        "one;PRODUCT;Alpha;Brand;2;A1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.header == ["handle", "fieldType", "name", "brand", "inventory", "sku"]
    assert batch.matched_count == 1
    assert batch.rows[0]["inventory"] == "1"


def test_build_inventory_update_batch_accepts_wix_header_case_variants(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;A1;1\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,FieldType,name,Brand,Inventory,SKU,PlainDescription\n"
        "one,PRODUCT,Alpha,Brand,2,A1,Specs\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.header == [
        "handle",
        "fieldType",
        "name",
        "brand",
        "inventory",
        "sku",
        "plainDescription",
    ]
    assert batch.matched_count == 1
    assert batch.rows[0]["inventory"] == "1"
    assert batch.rows[0]["sku"] == "A1"


def test_build_inventory_update_batch_accepts_columntextbox_diamond_export(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "catalog_products.csv"
    diamond_csv.write_text(
        "ColumnTextBox1;ColumnTextBox2;ColumnTextBox3;ColumnTextBox4;ColumnTextBox5;ColumnTextBox6;ColumnTextBox7;ColumnTextBox8;ColumnTextBox9;ColumnTextBox10;ColumnTextBox11\n"
        "Am Bogen;Schmuck;Beads & Charms;Thomas Sabo;Charm Club;111819;Charm Flügel;0613-001-12;1;21.15;55.00\n",
        encoding="cp1252",
    )

    wix_csv = tmp_path / "catalog_productswix.csv"
    wix_csv.write_text(
        "\ufeffhandle,fieldType,name,brand,plainDescription,inventory,sku\n"
        'ds-111819,PRODUCT,Thomas Sabo,Thomas Sabo,"Referenz: 0613-001-12",2,111819\n',
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Thomas Sabo"],
    )

    assert batch.matched_count == 1
    assert batch.changed_count == 1
    assert batch.rows[0]["handle"] == "ds-111819"
    assert batch.rows[0]["inventory"] == "1"
    assert batch.results[0].original_inventory == "2"
    assert batch.results[0].updated_inventory == "1"


def test_build_inventory_update_batch_normalizes_excel_sku_formatting(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;'111819;1\n"
        'Droz;Brand;="222333";2\n',
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,2,111819.0\n"
        "two,PRODUCT,Beta,Brand,1,222333\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.matched_count == 2
    assert [row["inventory"] for row in batch.rows] == ["1", "2"]


def test_build_inventory_update_batch_rejects_unrecognized_inventory_export(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "not_inventory.csv"
    diamond_csv.write_text(
        "ColumnTextBox1;ColumnTextBox2\n"
        "foo;bar\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,2,A1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="keine erkennbaren Artikelnummern"):
        build_inventory_update_batch(
            wix_export_csv=wix_csv,
            diamond_csv=diamond_csv,
            brands=["Brand"],
        )


def test_build_inventory_update_batch_creates_new_rows_for_unmatched_diamond_products(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge;Einstand;Verkauf;Produktlinie;Kurzbeschreibung;Referenz\n"
        "Am Bogen;Brand;A1;1;5;10;Line;Existing;R1\n"
        "Droz;Brand;A2;2;6;12;Line;New Product;R2\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,plainDescription,price,cost,inventory,sku,barcode\n"
        "one,PRODUCT,Alpha,Brand,Old,10,5,9,A1,R1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.has_blocking_errors is False
    assert batch.warning_count == 0
    assert batch.new_product_count == 1
    assert batch.unmatched_diamond_count == 0
    assert len(batch.rows) == 2
    assert batch.rows[1]["sku"] == "A2"
    assert batch.rows[1]["inventory"] == "2"
    assert batch.rows[1]["plainDescription"] == (
        "Verfügbar in der Bijouterie Droz in Zofingen AG"
    )
    assert batch.results[0].is_new_product is True
    assert batch.results[0].wix_row["sku"] == "A2"
    assert batch.results[1].is_new_product is False


def test_build_inventory_update_batch_rewrites_new_barcodes_that_exist_in_wix(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge;Einstand;Verkauf;Produktlinie;Kurzbeschreibung;Referenz\n"
        "Am Bogen;Brand;A1;1;5;10;Line;Existing;REF-1\n"
        "Droz;Brand;A2;2;6;12;Line;New Product;REF-1\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,plainDescription,price,cost,inventory,sku,barcode\n"
        "one,PRODUCT,Alpha,Brand,Old,10,5,9,A1,REF-1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.has_blocking_errors is False
    assert batch.new_product_count == 1
    assert batch.rows[0]["barcode"] == "REF-1"
    assert batch.rows[1]["sku"] == "A2"
    assert batch.rows[1]["barcode"] == "A2"
    assert len({row["barcode"] for row in batch.rows if row.get("barcode")}) == 2


def test_build_inventory_update_batch_blocks_invalid_new_products(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge;Einstand;Verkauf;Produktlinie;Kurzbeschreibung\n"
        "Am Bogen;Brand;A1;1;5;10;Line;Existing\n"
        "Droz;Brand;A2;2;6;;Line;New Product\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,price,cost,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,10,5,9,A1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.has_blocking_errors is True
    assert batch.new_product_count == 0
    assert len(batch.rows) == 1
    assert batch.issue_rows[0].kind == "new_product"
    assert any(issue.field == "price" for issue in batch.issue_rows[0].issues)


def test_build_inventory_update_batch_blocks_missing_configured_brands(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;A1;1\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,9,A1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand", "Other"],
    )

    assert batch.has_blocking_errors is True
    assert batch.error_count == 2
    assert {row.source["Datei"] for row in batch.issue_rows if row.has_errors} == {
        "Wix-Export",
        "DIAMOND-Export",
    }


def test_build_inventory_update_batch_blocks_unknown_diamond_brands(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;A1;1\n"
        "Droz;Unexpected;A2;2\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,9,A1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.has_blocking_errors is True
    assert batch.error_count == 1
    assert all("unbekannte Marke" in row.issues[0].message for row in batch.issue_rows)


def test_build_inventory_update_batch_preserves_unmanaged_wix_brands(
    tmp_path: Path,
) -> None:
    diamond_csv = tmp_path / "lager.csv"
    diamond_csv.write_text(
        "Filiale;Marke;Artikel Nr;Menge\n"
        "Am Bogen;Brand;A1;1\n",
        encoding="utf-8",
    )

    wix_csv = tmp_path / "catalog_products.csv"
    wix_csv.write_text(
        "handle,fieldType,name,brand,plainDescription,inventory,sku\n"
        "one,PRODUCT,Alpha,Brand,Managed old text,9,A1\n"
        "two,PRODUCT,Beta,Additional Import,Unmanaged text,5,X1\n",
        encoding="utf-8",
    )

    batch = build_inventory_update_batch(
        wix_export_csv=wix_csv,
        diamond_csv=diamond_csv,
        brands=["Brand"],
    )

    assert batch.has_blocking_errors is False
    assert batch.error_count == 0
    assert batch.matched_count == 1
    assert batch.set_to_zero_count == 0
    assert batch.changed_count == 1
    assert batch.rows[0]["inventory"] == "1"
    assert batch.rows[1]["inventory"] == "5"
    assert batch.rows[1]["plainDescription"] == "Unmanaged text"
    assert batch.results[1].source_kind == "wix_unmanaged"
    assert batch.results[1].updated_inventory == "5"
    assert batch.results[1].changed is False
