from zeitshop_converter.core import ConversionOptions, DiamondRecord, convert_records


def _template_header() -> list[str]:
    return [
        "handle",
        "fieldType",
        "name",
        "visible",
        "plainDescription",
        "brand",
        "price",
        "cost",
        "inventory",
        "sku",
        "barcode",
    ]


def test_pipeline_maps_valid_and_invalid_rows() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Product",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Uhr",
                "Kategorie": "Herrenuhr",
            },
        ),
        DiamondRecord(
            source_row=3,
            data={
                "Artikel Nr": "124",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Broken",
                "Verkauf": "abc",
                "Einstand": "20",
                "Menge": "1",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert len(batch.results) == 2
    assert len(batch.valid_rows) == 1
    assert len(batch.error_rows) == 1

    valid = batch.valid_rows[0]
    assert valid["fieldType"] == "PRODUCT"
    assert valid["price"] == "99.00"
    assert valid["inventory"] == "3"


def test_pipeline_merges_duplicate_article_numbers() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "DUP-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "One",
                "Verkauf": "10",
                "Einstand": "5",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=3,
            data={
                "Artikel Nr": "DUP-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Two",
                "Verkauf": "11",
                "Einstand": "5.5",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    assert len(batch.results) == 1
    row = batch.results[0].wix_row
    assert row["sku"] == "DUP-1"
    assert row["inventory"] == "3"


def test_pipeline_builds_non_duplicated_names() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "1",
                "Marke": "Maurice Lacroix",
                "Produktlinie": "Pontos",
                "Kurzbeschreibung": "Pontos",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=3,
            data={
                "Artikel Nr": "2",
                "Marke": "Maurice Lacroix",
                "Produktlinie": "Aikon",
                "Kurzbeschreibung": "Maurice Lacroix Aikon",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=4,
            data={
                "Artikel Nr": "3",
                "Marke": "Maurice Lacroix",
                "Produktlinie": "1975",
                "Kurzbeschreibung": "1975 Chrono",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=5,
            data={
                "Artikel Nr": "4",
                "Marke": "Thomas Sabo",
                "Produktlinie": "Charm Club",
                "Kurzbeschreibung": "Charm Kreuz",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=6,
            data={
                "Artikel Nr": "5",
                "Marke": "Thomas Sabo",
                "Produktlinie": "Charm Club",
                "Kurzbeschreibung": "Charms Buchstaben W",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    names = [result.wix_row["name"] for result in batch.results]
    assert names == [
        "Maurice Lacroix Pontos",
        "Maurice Lacroix Aikon",
        "Maurice Lacroix 1975 Chrono",
        "Thomas Sabo Charm Club Kreuz",
        "Thomas Sabo Charm Club Buchstaben W",
    ]


def test_pipeline_keeps_customer_facing_name_and_stores_reference_in_barcode() -> None:
    records = [
        DiamondRecord(
            source_row=10,
            data={
                "Artikel Nr": "A1",
                "Referenz": "AI1106-SS002-350-1",
                "Marke": "Maurice Lacroix",
                "Produktlinie": "Aikon",
                "Kurzbeschreibung": "Maurice Lacroix Aikon",
                "Verkauf": "1100",
                "Einstand": "495",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=11,
            data={
                "Artikel Nr": "A2",
                "Referenz": "AI1108-PVP02-130-1",
                "Marke": "Maurice Lacroix",
                "Produktlinie": "Aikon",
                "Kurzbeschreibung": "Maurice Lacroix Aikon",
                "Verkauf": "1100",
                "Einstand": "550",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    assert len(batch.results) == 2
    names = [r.wix_row["name"] for r in batch.results]
    assert names[0] == "Maurice Lacroix Aikon"
    assert names[1] == "Maurice Lacroix Aikon"
    assert batch.results[0].wix_row["barcode"] == "AI1106-SS002-350-1"
    assert batch.results[1].wix_row["barcode"] == "AI1108-PVP02-130-1"


def test_pipeline_merges_same_article_even_with_different_reference() -> None:
    records = [
        DiamondRecord(
            source_row=20,
            data={
                "Artikel Nr": "ART-1",
                "Referenz": "REF-ONE",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model A",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=21,
            data={
                "Artikel Nr": "ART-1",
                "Referenz": "REF-TWO",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model B",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    assert len(batch.results) == 1
    row = batch.results[0].wix_row
    assert row["sku"] == "ART-1"
    assert row["inventory"] == "3"
