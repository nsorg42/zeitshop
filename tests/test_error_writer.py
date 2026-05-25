import csv
from pathlib import Path

import pytest

from zeitshop_converter.core import Severity, ValidationIssue, WixRowResult
from zeitshop_converter.io import error_writer


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("fieldType must be PRODUCT for product rows.", "Der Feldtyp muss für Produktzeilen PRODUCT sein."),
        ("name is required.", "Der Produktname fehlt."),
        ("price must be numeric.", "Der Verkaufspreis muss numerisch sein."),
        ("Duplicate handle detected. Auto-adjusted to 'ds-ab-2'.", "Doppelter Handle erkannt. Automatisch angepasst zu 'ds-ab-2'."),
        ("invalid decimal value: 'abc'", "Ungültiger Dezimalwert: 'abc'"),
        ("invalid quantity value: '1.5'", "Ungültiger Mengenwert: '1.5'"),
        ("some unknown message", "some unknown message"),
    ],
)
def test_message_de_translates_known_messages(message: str, expected: str) -> None:
    issue = ValidationIssue(source_row=2, field="field", severity=Severity.WARNING, message=message)

    assert error_writer._message_de(issue) == expected


def test_write_issue_csv_writes_all_issues_with_translated_messages(tmp_path: Path) -> None:
    path = tmp_path / "issues.csv"
    issue_rows = [
        WixRowResult(
            source_row=2,
            source={"Artikel Nr": "A-1", "Marke": "Brand"},
            wix_row={},
            issues=[
                ValidationIssue(source_row=2, field="price", severity=Severity.ERROR, message="price is required."),
                ValidationIssue(
                    source_row=2,
                    field="handle",
                    severity=Severity.WARNING,
                    message="Duplicate handle detected. Auto-adjusted to 'ds-a-1-2'.",
                ),
            ],
        ),
        WixRowResult(
            source_row=3,
            source={"Referenz": "REF-3"},
            wix_row={},
            issues=[ValidationIssue(source_row=3, field="brand", severity=Severity.WARNING, message="unknown")],
        ),
    ]

    written = error_writer.write_issue_csv(path, issue_rows)

    assert written == 3
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["source_row"] == "2"
    assert rows[0]["Artikel Nr"] == "A-1"
    assert rows[0]["Marke"] == "Brand"
    assert rows[0]["Referenz"] == ""
    assert rows[0]["problem_schwere"] == "Fehler"
    assert rows[0]["problem"] == "Der Verkaufspreis fehlt."
    assert rows[1]["problem_schwere"] == "Warnung"
    assert "Doppelter Handle erkannt." in rows[1]["problem"]
    assert rows[2]["Referenz"] == "REF-3"
    assert rows[2]["problem_feld"] == "brand"
    assert rows[2]["problem"] == "unknown"


def test_write_error_csv_is_alias_for_issue_writer(tmp_path: Path) -> None:
    path = tmp_path / "errors.csv"
    rows = [
        WixRowResult(
            source_row=5,
            source={"Artikel Nr": "A-5"},
            wix_row={},
            issues=[ValidationIssue(source_row=5, field="price", severity=Severity.ERROR, message="price is required.")],
        )
    ]

    written = error_writer.write_error_csv(path, rows)

    assert written == 1
    assert path.exists()
