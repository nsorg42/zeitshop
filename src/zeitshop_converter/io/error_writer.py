from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Sequence

from ..core.models import Severity, ValidationIssue, WixRowResult

_DUP_HANDLE_RE = re.compile(r"^Duplicate handle detected\. Auto-adjusted to '(.+)'\.$")
_DUP_SKU_RE = re.compile(r"^Duplicate SKU detected: '(.+)'\.$")
_INVALID_DECIMAL_RE = re.compile(r"^invalid decimal value: (.+)$")
_INVALID_QTY_RE = re.compile(r"^invalid quantity value: (.+)$")


def _severity_de(severity: Severity) -> str:
    """Translate internal severity enum into German labels."""
    if severity == Severity.ERROR:
        return "Fehler"
    return "Warnung"


def _message_de(issue: ValidationIssue) -> str:
    """Translate known issue messages from English to German for reports."""
    message = issue.message

    if message == "fieldType must be PRODUCT for alpha conversion mode.":
        return "Der Feldtyp muss PRODUCT sein (Alpha-Modus)."
    if message == "name is required.":
        return "Der Produktname fehlt."
    if message == "name exceeds 80 characters.":
        return "Der Produktname ist länger als 80 Zeichen."
    if message == "Product name exceeded 80 characters and was truncated.":
        return "Der Produktname war länger als 80 Zeichen und wurde gekürzt."
    if message == "visible must be TRUE or FALSE.":
        return "Sichtbarkeit muss TRUE oder FALSE sein."
    if message == "price is required.":
        return "Der Verkaufspreis fehlt."
    if message == "price must be numeric.":
        return "Der Verkaufspreis muss numerisch sein."
    if message == "inventory is required.":
        return "Der Bestand fehlt."
    if message == "inventory must be IN_STOCK, OUT_OF_STOCK, or an integer.":
        return "Bestand muss IN_STOCK, OUT_OF_STOCK oder eine ganze Zahl sein."
    if message == "cost must be numeric with <=9 whole digits and <=2 decimals.":
        return "Einstand muss numerisch sein (max. 9 Vorkomma- und 2 Nachkommastellen)."
    if message == "sku exceeds 40 characters.":
        return "Die SKU ist länger als 40 Zeichen."
    if message == "brand exceeds 50 characters.":
        return "Die Marke ist länger als 50 Zeichen."

    match = _DUP_HANDLE_RE.match(message)
    if match:
        return f"Doppelter Handle erkannt. Automatisch angepasst zu '{match.group(1)}'."

    match = _DUP_SKU_RE.match(message)
    if match:
        return f"Doppelte SKU erkannt: '{match.group(1)}'."

    match = _INVALID_DECIMAL_RE.match(message)
    if match:
        return f"Ungültiger Dezimalwert: {match.group(1)}"

    match = _INVALID_QTY_RE.match(message)
    if match:
        return f"Ungültiger Mengenwert: {match.group(1)}"

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
