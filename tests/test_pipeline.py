from collections import Counter

import pytest

from zeitshop_converter.core import ConversionOptions, DiamondRecord, Severity, convert_records


def _template_header() -> list[str]:
    return [
        "handle",
        "fieldType",
        "name",
        "visible",
        "plainDescription",
        "categorySlugs",
        "primaryCategorySlug",
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
                "Warengruppe": "Category-A",
                "Kategorie": "Group-A",
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


def test_pipeline_builds_lager_plain_description_with_reference_and_availability() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            source_format="lager_csv",
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Filiale": "Am Bogen",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Category-A",
                "Kategorie": "Group-A",
            },
        )
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert (
        batch.valid_rows[0]["plainDescription"]
        == "Referenz: R-1\nVerfügbar in dem Ladengeschäft Bijouterie Am Bogen in Bremgarten AG"
    )


def test_pipeline_maps_kategorie_and_warengruppe_to_wix_categories() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Herrenuhr",
                "Kategorie": "Uhr",
            },
        )
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert batch.valid_rows[0]["primaryCategorySlug"] == "uhren"
    assert batch.valid_rows[0]["categorySlugs"] == "uhren;herrenuhren;brand"


def test_pipeline_normalizes_mixed_herren_damen_category_syntax() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Herren / Damenuhr",
                "Kategorie": "Uhr",
            },
        )
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert batch.valid_rows[0]["categorySlugs"] == "uhren;herrenuhren;damenuhren;brand"


def test_pipeline_ignores_armbanduhren_category() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Armbanduhr",
                "Kategorie": "Uhr",
            },
        )
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert batch.valid_rows[0]["primaryCategorySlug"] == "uhren"
    assert batch.valid_rows[0]["categorySlugs"] == "uhren;brand"


def test_pipeline_pluralizes_collier_category() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Collier",
                "Kategorie": "Schmuck",
            },
        )
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert batch.valid_rows[0]["primaryCategorySlug"] == "schmuck"
    assert batch.valid_rows[0]["categorySlugs"] == "schmuck;colliers;brand"


def test_pipeline_pluralizes_ring_category() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Ring",
                "Kategorie": "Schmuck",
            },
        )
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert batch.valid_rows[0]["primaryCategorySlug"] == "schmuck"
    assert batch.valid_rows[0]["categorySlugs"] == "schmuck;ringe;brand"


def test_pipeline_preserves_eichmueller_brand_category_label() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "123",
                "Referenz": "R-1",
                "Marke": "Eichmüller",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "99",
                "Einstand": "40.50",
                "Menge": "3",
                "Warengruppe": "Wecker",
                "Kategorie": "Uhr",
            },
        )
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert batch.valid_rows[0]["primaryCategorySlug"] == "uhren"
    assert batch.valid_rows[0]["categorySlugs"] == "uhren;wecker;eichmüller"


def test_pipeline_merges_duplicate_article_numbers_when_only_branch_and_quantity_differ() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "DUP-1",
                "Referenz": "REF-1",
                "Filiale": "Store-North",
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
                "Referenz": "REF-1",
                "Filiale": "Store-South",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "One",
                "Verkauf": "10",
                "Einstand": "5",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    assert len(batch.results) == 1
    result = batch.results[0]
    row = result.wix_row
    assert row["sku"] == "DUP-1"
    assert row["inventory"] == "3"
    assert not any(issue.field == "merge" for issue in result.issues)


def test_pipeline_merges_lager_branches_into_combined_availability_text() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            source_format="lager_csv",
            data={
                "Artikel Nr": "DUP-1",
                "Referenz": "REF-1",
                "Filiale": "Am Bogen",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "10",
                "Einstand": "5",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=3,
            source_format="lager_csv",
            data={
                "Artikel Nr": "DUP-1",
                "Referenz": "REF-1",
                "Filiale": "Droz",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "",
                "Verkauf": "10",
                "Einstand": "5",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert len(batch.results) == 1
    assert (
        batch.results[0].wix_row["plainDescription"]
        == "Referenz: REF-1\nVerfügbar in den Ladengeschäften Bijouterie Am Bogen in Bremgarten AG "
        "und in der Bijouterie Droz in Zofingen AG"
    )


def test_pipeline_builds_non_duplicated_names() -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Artikel Nr": "1",
                "Marke": "Atlas Forge",
                "Produktlinie": "Northline",
                "Kurzbeschreibung": "Northline",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=3,
            data={
                "Artikel Nr": "2",
                "Marke": "Atlas Forge",
                "Produktlinie": "Skyframe",
                "Kurzbeschreibung": "Atlas Forge Skyframe",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=4,
            data={
                "Artikel Nr": "3",
                "Marke": "Atlas Forge",
                "Produktlinie": "Series 77",
                "Kurzbeschreibung": "77 Chrono",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=5,
            data={
                "Artikel Nr": "4",
                "Marke": "Copper Lane",
                "Produktlinie": "Token Club",
                "Kurzbeschreibung": "Token Cross",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=6,
            data={
                "Artikel Nr": "5",
                "Marke": "Copper Lane",
                "Produktlinie": "Token Club",
                "Kurzbeschreibung": "Tokens Letter W",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    names = [result.wix_row["name"] for result in batch.results]
    assert names == [
        "Atlas Forge Northline",
        "Atlas Forge Skyframe",
        "Atlas Forge Series 77 Chrono",
        "Copper Lane Token Club Cross",
        "Copper Lane Token Club Letter W",
    ]


def test_pipeline_keeps_customer_facing_name_and_stores_reference_in_barcode() -> None:
    records = [
        DiamondRecord(
            source_row=10,
            data={
                "Artikel Nr": "A1",
                "Referenz": "ZX-1001-ALPHA",
                "Marke": "Atlas Forge",
                "Produktlinie": "Skyframe",
                "Kurzbeschreibung": "Atlas Forge Skyframe",
                "Verkauf": "1100",
                "Einstand": "495",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=11,
            data={
                "Artikel Nr": "A2",
                "Referenz": "ZX-1002-BRAVO",
                "Marke": "Atlas Forge",
                "Produktlinie": "Skyframe",
                "Kurzbeschreibung": "Atlas Forge Skyframe",
                "Verkauf": "1100",
                "Einstand": "550",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    assert len(batch.results) == 2
    names = [r.wix_row["name"] for r in batch.results]
    assert names[0] == "Atlas Forge Skyframe"
    assert names[1] == "Atlas Forge Skyframe"
    assert batch.results[0].wix_row["barcode"] == "ZX-1001-ALPHA"
    assert batch.results[1].wix_row["barcode"] == "ZX-1002-BRAVO"


def test_pipeline_rewrites_duplicate_barcodes_to_unique_values() -> None:
    records = [
        DiamondRecord(
            source_row=12,
            data={
                "Artikel Nr": "SKU-1",
                "Referenz": "BAR-1",
                "Marke": "Atlas Forge",
                "Produktlinie": "Skyframe",
                "Kurzbeschreibung": "One",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=13,
            data={
                "Artikel Nr": "SKU-2",
                "Referenz": "BAR-1",
                "Marke": "Atlas Forge",
                "Produktlinie": "Skyframe",
                "Kurzbeschreibung": "Two",
                "Verkauf": "120",
                "Einstand": "60",
                "Menge": "1",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert len(batch.results) == 2
    assert batch.error_count == 0
    assert batch.warning_count == 0
    assert len(batch.valid_product_rows) == 2
    assert batch.results[0].wix_row["barcode"] == "SKU-1"
    assert batch.results[1].wix_row["barcode"] == "SKU-2"


def test_pipeline_does_not_merge_same_article_when_reference_differs() -> None:
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
    assert len(batch.results) == 2
    assert batch.error_count == 0
    assert batch.warning_count == 2
    assert [result.wix_row["inventory"] for result in batch.results] == ["1", "2"]

    for result in batch.results:
        warning = next(issue for issue in result.issues if issue.field == "merge")
        assert warning.severity == Severity.WARNING
        assert "Duplicate identity 'ART-1'" in warning.message
        assert "Referenz" in warning.message

    assert any(issue.field == "sku" for issue in batch.results[1].issues)


@pytest.mark.parametrize(
    ("field", "left", "right"),
    [
        ("Kurzbeschreibung", "Model A", "Model B"),
        ("Einstand", "50", "51.00"),
        ("Verkauf", "100", "101.00"),
    ],
)
def test_pipeline_does_not_merge_duplicates_that_disagree_on_critical_fields(
    field: str,
    left: str,
    right: str,
) -> None:
    first = {
        "Artikel Nr": "WARN-1",
        "Referenz": "REF-1",
        "Marke": "Brand",
        "Produktlinie": "Line",
        "Kurzbeschreibung": "Model A",
        "Verkauf": "100",
        "Einstand": "50",
        "Menge": "1",
    }
    second = dict(first)
    second["Menge"] = "2"
    first[field] = left
    second[field] = right

    batch = convert_records(
        [
            DiamondRecord(source_row=30, data=first),
            DiamondRecord(source_row=31, data=second),
        ],
        _template_header(),
        ConversionOptions(),
    )

    assert len(batch.results) == 2
    assert batch.error_count == 0
    assert batch.warning_count == 2
    assert [result.wix_row["inventory"] for result in batch.results] == ["1", "2"]

    for result in batch.results:
        warning = next(issue for issue in result.issues if issue.field == "merge")
        assert warning.severity == Severity.WARNING
        assert "source rows 30, 31" in warning.message
        assert field in warning.message

    assert [result.wix_row["barcode"] for result in batch.results] == ["WARN-1", "ds-warn-1-2"]


def test_pipeline_does_not_warn_for_equivalent_decimal_formats_in_merged_rows() -> None:
    records = [
        DiamondRecord(
            source_row=40,
            data={
                "Artikel Nr": "DEC-1",
                "Referenz": "REF-DEC",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=41,
            data={
                "Artikel Nr": "DEC-1",
                "Referenz": "REF-DEC",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model",
                "Verkauf": "100.00",
                "Einstand": "50.00",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert len(batch.results) == 1
    result = batch.results[0]
    assert result.wix_row["inventory"] == "3"
    assert not any(issue.field == "merge" for issue in result.issues)


def test_pipeline_does_not_merge_duplicate_rows_when_quantity_is_invalid() -> None:
    records = [
        DiamondRecord(
            source_row=45,
            data={
                "Artikel Nr": "QTY-1",
                "Referenz": "REF-QTY",
                "Filiale": "Store-North",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "abc",
            },
        ),
        DiamondRecord(
            source_row=46,
            data={
                "Artikel Nr": "QTY-1",
                "Referenz": "REF-QTY",
                "Filiale": "Store-South",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert len(batch.results) == 2
    assert batch.error_count == 1
    assert batch.warning_count == 2

    invalid_result = batch.results[0]
    second_result = batch.results[1]

    invalid_warning = next(issue for issue in invalid_result.issues if issue.field == "merge")
    assert "invalid merge values" in invalid_warning.message
    assert "row 45 (Menge)" in invalid_warning.message
    assert any(
        issue.field == "inventory" and issue.severity == Severity.ERROR
        for issue in invalid_result.issues
    )

    second_warning = next(issue for issue in second_result.issues if issue.field == "merge")
    assert "invalid merge values" in second_warning.message
    assert second_result.wix_row["inventory"] == "2"
    assert invalid_result.wix_row["barcode"] == "QTY-1"
    assert second_result.wix_row["barcode"] == "ds-qty-1-2"


def test_pipeline_reports_invalid_numeric_fields_once() -> None:
    records = [
        DiamondRecord(
            source_row=50,
            data={
                "Artikel Nr": "BAD-1",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Broken",
                "Verkauf": "abc",
                "Einstand": "def",
                "Menge": "1.5",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())
    issue_counts = Counter(issue.field for issue in batch.results[0].issues)

    assert issue_counts == Counter({"price": 1, "cost": 1, "inventory": 1})


def test_pipeline_requires_artikel_nr_and_does_not_fallback_to_referenz() -> None:
    records = [
        DiamondRecord(
            source_row=60,
            data={
                "Artikel Nr": "",
                "Referenz": "REF-ONLY",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model A",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "1",
            },
        ),
        DiamondRecord(
            source_row=61,
            data={
                "Artikel Nr": "",
                "Referenz": "REF-ONLY",
                "Marke": "Brand",
                "Produktlinie": "Line",
                "Kurzbeschreibung": "Model A",
                "Verkauf": "100",
                "Einstand": "50",
                "Menge": "2",
            },
        ),
    ]

    batch = convert_records(records, _template_header(), ConversionOptions())

    assert len(batch.results) == 2
    assert batch.error_count == 2
    assert batch.warning_count == 0
    assert [result.wix_row["sku"] for result in batch.results] == ["", ""]
    assert [result.wix_row["barcode"] for result in batch.results] == ["ds-60", "ds-61"]
    for result in batch.results:
        assert any(issue.field == "sku" and issue.message == "sku is required." for issue in result.issues)
