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


def test_pipeline_warns_on_duplicate_sku() -> None:
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
                "Menge": "1",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    second = batch.results[1]
    assert second.has_warnings
    assert any("Duplicate SKU detected" in issue.message for issue in second.issues)
