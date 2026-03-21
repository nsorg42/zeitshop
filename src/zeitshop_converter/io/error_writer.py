from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Sequence

from ..core.models import Severity, ValidationIssue, WixRowResult

_DUP_HANDLE_RE = re.compile(r"^Duplicate handle detected\. Auto-adjusted to '(.+)'\.$")
_DUP_SKU_RE = re.compile(r"^Duplicate SKU detected: '(.+)'\.$")
_UNMERGED_IDENTITY_RE = re.compile(
    r"^Duplicate identity '(.+)' was not merged across source rows (.+) because (.+)\.$"
)
_INVALID_DECIMAL_RE = re.compile(r"^invalid decimal value: (.+)$")
_INVALID_QTY_RE = re.compile(r"^invalid quantity value: (.+)$")
_IMAGE_REF_RE = re.compile(r"^Image reference could not be resolved: '(.+)'\.$")
_UNSUPPORTED_IMAGE_RE = re.compile(r"^Unsupported image file type: '(.+)'\.$")
_LOCAL_IMAGE_NO_UPLOAD_RE = re.compile(
    r"^Local image found but Wix upload is not configured: '(.+)'\. "
    r"Set a Wix site ID and API key to migrate local files automatically\.$"
)
_IMAGE_UPLOAD_FAILED_RE = re.compile(r"^Failed to upload image '(.+)' to Wix: (.+)$")
_EXACT_MESSAGE_TRANSLATIONS = {
    "fieldType must be PRODUCT for product rows.": "Der Feldtyp muss für Produktzeilen PRODUCT sein.",
    "name is required.": "Der Produktname fehlt.",
    "name exceeds 80 characters.": "Der Produktname ist länger als 80 Zeichen.",
    "Product name exceeded 80 characters and was truncated.": "Der Produktname war länger als 80 Zeichen und wurde gekürzt.",
    "visible must be TRUE or FALSE.": "Sichtbarkeit muss TRUE oder FALSE sein.",
    "price is required.": "Der Verkaufspreis fehlt.",
    "price must be numeric.": "Der Verkaufspreis muss numerisch sein.",
    "inventory is required.": "Der Bestand fehlt.",
    "inventory must be IN_STOCK, OUT_OF_STOCK, or an integer.": "Bestand muss IN_STOCK, OUT_OF_STOCK oder eine ganze Zahl sein.",
    "cost must be numeric with <=9 whole digits and <=2 decimals.": "Einstand muss numerisch sein (max. 9 Vorkomma- und 2 Nachkommastellen).",
    "sku exceeds 40 characters.": "Die SKU ist länger als 40 Zeichen.",
    "brand exceeds 50 characters.": "Die Marke ist länger als 50 Zeichen.",
}


def _severity_de(severity: Severity) -> str:
    """Translate internal severity enum into German labels."""
    if severity == Severity.ERROR:
        return "Fehler"
    return "Warnung"


def _message_de(issue: ValidationIssue) -> str:
    """Translate known issue messages from English to German for reports."""
    message = issue.message

    translated = _EXACT_MESSAGE_TRANSLATIONS.get(message)
    if translated is not None:
        return translated

    match = _DUP_HANDLE_RE.match(message)
    if match:
        return f"Doppelter Handle erkannt. Automatisch angepasst zu '{match.group(1)}'."

    match = _DUP_SKU_RE.match(message)
    if match:
        return f"Doppelte SKU erkannt: '{match.group(1)}'."

    match = _UNMERGED_IDENTITY_RE.match(message)
    if match:
        reason = match.group(3)
        reason = reason.replace("conflicting fields:", "abweichende Felder:")
        reason = reason.replace("invalid merge values:", "ungültige Merge-Werte:")
        reason = reason.replace("row ", "Zeile ")
        reason = reason.replace("merge requirements were not met", "die Merge-Bedingungen nicht erfüllt wurden")
        return (
            f"Produktidentität '{match.group(1)}' wurde über Quellzeilen {match.group(2)} "
            f"nicht zusammengeführt: {reason}."
        )

    match = _INVALID_DECIMAL_RE.match(message)
    if match:
        return f"Ungültiger Dezimalwert: {match.group(1)}"

    match = _INVALID_QTY_RE.match(message)
    if match:
        return f"Ungültiger Mengenwert: {match.group(1)}"

    match = _IMAGE_REF_RE.match(message)
    if match:
        return f"Bildreferenz konnte nicht aufgelöst werden: '{match.group(1)}'."

    match = _UNSUPPORTED_IMAGE_RE.match(message)
    if match:
        return f"Nicht unterstützter Bildtyp: '{match.group(1)}'."

    match = _LOCAL_IMAGE_NO_UPLOAD_RE.match(message)
    if match:
        return (
            f"Lokales Bild gefunden, aber der Wix-Upload ist nicht konfiguriert: "
            f"'{match.group(1)}'."
        )

    match = _IMAGE_UPLOAD_FAILED_RE.match(message)
    if match:
        return f"Bild-Upload nach Wix fehlgeschlagen ({match.group(1)}): {match.group(2)}"

    return message


def write_issue_csv(path: str | Path, issue_rows: Sequence[WixRowResult]) -> int:
    """Write a German issue report with one output row per concrete issue.

    Each line keeps the source data columns first (problematische Zeile) and
    appends the translated issue metadata after it.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    source_fields: list[str] = []
    seen: set[str] = set()
    for result in issue_rows:
        for key in result.source.keys():
            if key not in seen:
                seen.add(key)
                source_fields.append(key)

    header = ["source_row", *source_fields, "problem_schwere", "problem_feld", "problem"]

    written = 0
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for result in issue_rows:
            for issue in result.issues:
                row = {
                    "source_row": str(result.source_row),
                    "problem_schwere": _severity_de(issue.severity),
                    "problem_feld": issue.field,
                    "problem": _message_de(issue),
                }
                for field in source_fields:
                    # Keep source cell values as stored in the parsed source row.
                    row[field] = result.source.get(field, "")
                writer.writerow(row)
                written += 1

    return written


def write_error_csv(path: str | Path, error_rows: Sequence[WixRowResult]) -> int:
    """Backwards-compatible alias for writing issue reports."""
    return write_issue_csv(path=path, issue_rows=error_rows)
