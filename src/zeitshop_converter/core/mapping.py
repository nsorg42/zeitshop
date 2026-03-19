from __future__ import annotations

from collections.abc import MutableMapping, Sequence

from .models import ConversionOptions, DiamondRecord, Severity, ValidationIssue
from .normalize import format_decimal, make_handle, normalize_inventory, normalize_text, parse_decimal


def _build_name(record: DiamondRecord) -> tuple[str, bool]:
    brand = normalize_text(record.data.get("Marke"))
    line = normalize_text(record.data.get("Produktlinie"))
    short = normalize_text(record.data.get("Kurzbeschreibung"))
    fallback = normalize_text(record.data.get("Artikel Nr"))

    name = normalize_text(" ".join(part for part in (brand, line, short) if part))
    if not name:
        name = fallback or f"product-{record.source_row}"

    if len(name) <= 80:
        return name, False

    return name[:80].rstrip(), True


def _build_plain_description(record: DiamondRecord) -> str:
    items: list[str] = []
    warengruppe = normalize_text(record.data.get("Warengruppe"))
    referenz = normalize_text(record.data.get("Referenz"))
    kategorie = normalize_text(record.data.get("Kategorie"))

    if warengruppe:
        items.append(f"Warengruppe: {warengruppe}")
    if referenz:
        items.append(f"Referenz: {referenz}")
    if kategorie:
        items.append(f"Kategorie: {kategorie}")

    return " | ".join(items)


def _dedupe_handle(base_handle: str, seen_handles: MutableMapping[str, int]) -> tuple[str, bool]:
    count = seen_handles.get(base_handle, 0) + 1
    seen_handles[base_handle] = count
    if count == 1:
        return base_handle, False
    return f"{base_handle}-{count}", True


def map_diamond_to_wix_row(
    record: DiamondRecord,
    template_header: Sequence[str],
    options: ConversionOptions,
    seen_handles: MutableMapping[str, int],
) -> tuple[dict[str, str], list[ValidationIssue]]:
    row = {column: "" for column in template_header}
    issues: list[ValidationIssue] = []

    article_nr = normalize_text(record.data.get("Artikel Nr"))
    referenz = normalize_text(record.data.get("Referenz"))

    base_handle_seed = article_nr or referenz or str(record.source_row)
    base_handle = make_handle(base_handle_seed, prefix=options.handle_prefix)
    handle, deduped = _dedupe_handle(base_handle, seen_handles)

    if deduped:
        issues.append(
            ValidationIssue(
                source_row=record.source_row,
                field="handle",
                severity=Severity.WARNING,
                message=f"Duplicate handle detected. Auto-adjusted to '{handle}'.",
            )
        )

    name, truncated = _build_name(record)
    if truncated:
        issues.append(
            ValidationIssue(
                source_row=record.source_row,
                field="name",
                severity=Severity.WARNING,
                message="Product name exceeded 80 characters and was truncated.",
            )
        )

    row["fieldType"] = "PRODUCT"
    row["handle"] = handle
    row["name"] = name
    row["visible"] = "TRUE" if options.default_visible else "FALSE"
    row["brand"] = normalize_text(record.data.get("Marke"))
    row["plainDescription"] = _build_plain_description(record)
    row["sku"] = article_nr or referenz

    try:
        row["price"] = format_decimal(parse_decimal(record.data.get("Verkauf")), places=2)
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                source_row=record.source_row,
                field="price",
                severity=Severity.ERROR,
                message=str(exc),
            )
        )

    try:
        row["cost"] = format_decimal(parse_decimal(record.data.get("Einstand")), places=2)
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                source_row=record.source_row,
                field="cost",
                severity=Severity.ERROR,
                message=str(exc),
            )
        )

    try:
        row["inventory"] = normalize_inventory(
            record.data.get("Menge"),
            numeric_inventory=options.numeric_inventory,
        )
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                source_row=record.source_row,
                field="inventory",
                severity=Severity.ERROR,
                message=str(exc),
            )
        )

    return row, issues
