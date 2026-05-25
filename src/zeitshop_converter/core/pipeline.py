from __future__ import annotations

from collections import Counter, defaultdict
from .barcodes import ensure_unique_product_barcodes
from .mapping import map_diamond_to_wix_row
from .models import (
    ConversionBatch,
    ConversionOptions,
    DiamondRecord,
    Severity,
    ValidationIssue,
    WixRowResult,
)
from .normalize import normalize_text, parse_decimal, parse_quantity
from .validation import validate_wix_row

_MERGE_ALLOWED_DIFFERENCE_FIELDS = frozenset({"Filiale", "Menge"})
_MERGE_DECIMAL_FIELDS = frozenset({"Einstand", "Verkauf"})
_MERGE_BLOCKER_FIELDS = ("Einstand", "Verkauf", "Menge")


def _record_identity(record: DiamondRecord) -> str:
    """Build a stable grouping key for duplicate rows.

    Artikel number is the primary identity.
    If unavailable we use source row, which keeps the row unique.
    """

    article_nr = normalize_text(record.data.get("Artikel Nr"))
    return article_nr or f"row-{record.source_row}"


def _merge_conflict_key(field: str, value: str | None) -> object:
    """Build a stable comparison key for strict merge compatibility checks."""

    text = normalize_text(value)
    if not text:
        return ""
    if field in _MERGE_DECIMAL_FIELDS:
        try:
            return parse_decimal(text)
        except ValueError:
            return text
    return text


def _merge_signature(record: DiamondRecord) -> tuple[tuple[str, object], ...]:
    """Return the strict merge signature for fields that must stay identical."""

    items: list[tuple[str, object]] = []
    for field in sorted(record.data):
        if field in _MERGE_ALLOWED_DIFFERENCE_FIELDS:
            continue
        items.append((field, _merge_conflict_key(field, record.data.get(field))))
    return tuple(items)


def _merge_blocker_fields(record: DiamondRecord) -> tuple[str, ...]:
    """Return fields whose invalid numeric values make merging unsafe."""

    blockers: list[str] = []
    for field in _MERGE_BLOCKER_FIELDS:
        text = normalize_text(record.data.get(field))
        if not text:
            continue
        try:
            if field == "Menge":
                parse_quantity(text)
            else:
                parse_decimal(text)
        except ValueError:
            blockers.append(field)
    return tuple(blockers)


def _conflicting_merge_fields(bucket: list[DiamondRecord]) -> list[str]:
    """List stable fields that differ inside one duplicate-identity bucket."""

    all_fields = sorted(
        {
            field
            for row in bucket
            for field in row.data
            if field not in _MERGE_ALLOWED_DIFFERENCE_FIELDS
        }
    )

    conflicts: list[str] = []
    for field in all_fields:
        values = {_merge_conflict_key(field, row.data.get(field)) for row in bucket}
        if len(values) > 1:
            conflicts.append(field)
    return conflicts


def _build_unmerged_bucket_warning(
    bucket: list[DiamondRecord],
    blocker_fields_by_row: dict[int, tuple[str, ...]],
    source_row: int,
) -> ValidationIssue:
    """Warn when rows share an identity but are not safe to merge."""

    identity = _record_identity(bucket[0])
    row_numbers = ", ".join(str(row.source_row) for row in bucket)
    reasons: list[str] = []

    conflict_fields = _conflicting_merge_fields(bucket)
    if conflict_fields:
        reasons.append(f"conflicting fields: {', '.join(conflict_fields)}")

    if blocker_fields_by_row:
        details = "; ".join(
            f"row {row_number} ({', '.join(fields)})"
            for row_number, fields in sorted(blocker_fields_by_row.items())
        )
        reasons.append(f"invalid merge values: {details}")

    reason_text = "; ".join(reasons) if reasons else "merge requirements were not met"
    return ValidationIssue(
        source_row=source_row,
        field="merge",
        severity=Severity.WARNING,
        message=(
            f"Duplicate identity '{identity}' was not merged across source rows {row_numbers} "
            f"because {reason_text}."
        ),
    )


def _merge_compatible_rows(rows: list[DiamondRecord]) -> DiamondRecord:
    """Merge rows that are already known to be compatible and safe."""

    base = rows[0]
    merged_data = dict(base.data)
    qty_total = 0
    qty_found = False
    branches: list[str] = []

    for row in rows:
        branch = normalize_text(row.data.get("Filiale"))
        if branch and branch not in branches:
            branches.append(branch)
        qty = parse_quantity(row.data.get("Menge"))
        if qty is not None:
            qty_total += qty
            qty_found = True

    if branches:
        merged_data["Filiale"] = " | ".join(branches)

    if qty_found:
        merged_data["Menge"] = str(max(qty_total, 0))

    return DiamondRecord(source_row=base.source_row, data=merged_data, source_format=base.source_format)


def _merge_records_by_identity(
    records: list[DiamondRecord],
) -> list[tuple[DiamondRecord, list[ValidationIssue]]]:
    """Merge duplicate DIAMOND rows that represent the same product.
    Rows are merged only when all stable product fields match exactly after
    normalization. Branch/location and quantity may differ."""

    grouped: dict[str, list[DiamondRecord]] = {}
    for record in records:
        key = _record_identity(record)
        grouped.setdefault(key, []).append(record)

    merged_records: list[tuple[DiamondRecord, list[ValidationIssue]]] = []
    for bucket in grouped.values():
        if len(bucket) == 1:
            merged_records.append((bucket[0], []))
            continue

        blocker_fields_by_row = {
            row.source_row: blockers
            for row in bucket
            if (blockers := _merge_blocker_fields(row))
        }
        signature_groups: dict[tuple[tuple[str, object], ...], list[DiamondRecord]] = defaultdict(list)
        for row in bucket:
            signature_groups[_merge_signature(row)].append(row)

        if len(signature_groups) == 1 and not blocker_fields_by_row:
            merged_records.append((_merge_compatible_rows(bucket), []))
            continue

        output_records: list[DiamondRecord] = []
        ordered_groups = sorted(
            signature_groups.values(),
            key=lambda rows: min(row.source_row for row in rows),
        )
        for group in ordered_groups:
            valid_rows = [row for row in group if row.source_row not in blocker_fields_by_row]
            invalid_rows = [row for row in group if row.source_row in blocker_fields_by_row]

            if len(valid_rows) > 1:
                output_records.append(_merge_compatible_rows(valid_rows))
            else:
                output_records.extend(valid_rows)

            output_records.extend(invalid_rows)

        output_records.sort(key=lambda record: record.source_row)
        for record in output_records:
            merged_records.append(
                (
                    record,
                    [_build_unmerged_bucket_warning(bucket, blocker_fields_by_row, source_row=record.source_row)],
                )
            )

    return merged_records


def convert_records(
    records: list[DiamondRecord],
    template_header: list[str],
    options: ConversionOptions | None = None,
) -> ConversionBatch:
    """Convert canonical DIAMOND records into Wix rows with validation issues."""

    active_options = options or ConversionOptions()
    merged_records = _merge_records_by_identity(records)
    seen_handles: Counter[str] = Counter()
    seen_skus: Counter[str] = Counter()
    results: list[WixRowResult] = []

    for record, merge_issues in merged_records:
        wix_row, issues = map_diamond_to_wix_row(
            record=record,
            template_header=template_header,
            options=active_options,
            seen_handles=seen_handles,
        )
        issues = [*merge_issues, *issues]
        sku = normalize_text(wix_row.get("sku"))
        if sku:
            seen_skus[sku] += 1
            if seen_skus[sku] > 1:
                issues.append(
                    ValidationIssue(
                        source_row=record.source_row,
                        field="sku",
                        severity=Severity.WARNING,
                        message=f"Duplicate SKU detected: '{sku}'.",
                    )
                )
        mapped_error_fields = {
            issue.field
            for issue in issues
            if issue.severity == Severity.ERROR
        }
        validation_issues = validate_wix_row(wix_row, source_row=record.source_row)
        if mapped_error_fields:
            validation_issues = [
                issue
                for issue in validation_issues
                if not (issue.severity == Severity.ERROR and issue.field in mapped_error_fields)
            ]

        issues.extend(validation_issues)
        results.append(
            WixRowResult(
                source_row=record.source_row,
                source=record.data,
                wix_row=wix_row,
                issues=issues,
            )
        )

    ensure_unique_product_barcodes(
        [(result.source_row, result.wix_row) for result in results]
    )

    return ConversionBatch(header=template_header, results=results)
