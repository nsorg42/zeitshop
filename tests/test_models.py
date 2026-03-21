from zeitshop_converter.core import ConversionBatch, Severity, ValidationIssue, WixRowResult


def test_wix_row_result_flags_errors_and_warnings() -> None:
    result = WixRowResult(
        source_row=2,
        source={},
        wix_row={},
        issues=[
            ValidationIssue(source_row=2, field="price", severity=Severity.ERROR, message="bad"),
            ValidationIssue(source_row=2, field="brand", severity=Severity.WARNING, message="warn"),
        ],
    )

    assert result.has_errors is True
    assert result.has_warnings is True


def test_conversion_batch_separates_valid_products_media_and_issue_counts() -> None:
    valid_with_media = WixRowResult(
        source_row=2,
        source={"Artikel Nr": "A-1"},
        wix_row={"handle": "one", "fieldType": "PRODUCT"},
        media_rows=[{"handle": "one", "fieldType": "MEDIA"}],
    )
    warning_with_media = WixRowResult(
        source_row=3,
        source={"Artikel Nr": "A-2"},
        wix_row={"handle": "two", "fieldType": "PRODUCT"},
        media_rows=[{"handle": "two", "fieldType": "MEDIA"}],
        issues=[ValidationIssue(source_row=3, field="brand", severity=Severity.WARNING, message="warn")],
    )
    invalid = WixRowResult(
        source_row=4,
        source={"Artikel Nr": "A-3"},
        wix_row={"handle": "three", "fieldType": "PRODUCT"},
        media_rows=[{"handle": "three", "fieldType": "MEDIA"}],
        issues=[ValidationIssue(source_row=4, field="price", severity=Severity.ERROR, message="bad")],
    )

    batch = ConversionBatch(header=["handle", "fieldType"], results=[valid_with_media, warning_with_media, invalid])

    assert batch.valid_product_rows == [
        {"handle": "one", "fieldType": "PRODUCT"},
        {"handle": "two", "fieldType": "PRODUCT"},
    ]
    assert batch.valid_rows == [
        {"handle": "one", "fieldType": "PRODUCT"},
        {"handle": "one", "fieldType": "MEDIA"},
        {"handle": "two", "fieldType": "PRODUCT"},
        {"handle": "two", "fieldType": "MEDIA"},
    ]
    assert batch.issue_rows == [warning_with_media, invalid]
    assert batch.error_rows == [invalid]
    assert batch.error_count == 1
    assert batch.warning_count == 1
