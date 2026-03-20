from __future__ import annotations

from collections import Counter
from collections import OrderedDict

from .mapping import map_diamond_to_wix_row
from .models import (
    ConversionBatch,
    ConversionOptions,
    DiamondRecord,
    Severity,
    ValidationIssue,
    WixRowResult,
)
from .normalize import normalize_text, parse_quantity
from .validation import validate_wix_row


def _record_identity(record: DiamondRecord) -> str:
    article_nr = normalize_text(record.data.get("Artikel Nr"))
    referenz = normalize_text(record.data.get("Referenz"))
    return article_nr or referenz or f"row-{record.source_row}"


def _merge_records_by_identity(records: list[DiamondRecord]) -> list[DiamondRecord]:
    grouped: OrderedDict[str, list[DiamondRecord]] = OrderedDict()
    for record in records:
        key = _record_identity(record)
        grouped.setdefault(key, []).append(record)

    merged_records: list[DiamondRecord] = []
    for bucket in grouped.values():
        if len(bucket) == 1:
            merged_records.append(bucket[0])
            continue

        base = bucket[0]
        merged_data = dict(base.data)

        qty_total = 0
        qty_found = False
        for row in bucket:
            try:
                qty = parse_quantity(row.data.get("Menge"))
            except ValueError:
                qty = None
            if qty is not None:
                qty_total += qty
                qty_found = True

            for field, value in row.data.items():
                if not normalize_text(merged_data.get(field)) and normalize_text(value):
                    merged_data[field] = value

        if qty_found:
            merged_data["Menge"] = str(max(qty_total, 0))

        merged_records.append(DiamondRecord(source_row=base.source_row, data=merged_data))

    return merged_records


def convert_records(
    records: list[DiamondRecord],
    template_header: list[str],
    options: ConversionOptions | None = None,
) -> ConversionBatch:
    active_options = options or ConversionOptions()
    merged_records = _merge_records_by_identity(records)
    seen_handles: Counter[str] = Counter()
    seen_skus: Counter[str] = Counter()
    results: list[WixRowResult] = []

    for record in merged_records:
        wix_row, issues = map_diamond_to_wix_row(
            record=record,
            template_header=template_header,
            options=active_options,
            seen_handles=seen_handles,
        )
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

        issues.extend(validate_wix_row(wix_row, source_row=record.source_row))
        results.append(
            WixRowResult(
                source_row=record.source_row,
                source=record.data,
                wix_row=wix_row,
                issues=issues,
            )
        )

    return ConversionBatch(header=template_header, results=results)
