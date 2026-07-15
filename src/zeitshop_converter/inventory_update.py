from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from .brand_storage import dedupe_brands, load_brands, normalize_brand_key
from .core import (
    ConversionOptions,
    DiamondRecord,
    InventoryUpdateBatch,
    InventoryUpdateIssueRow,
    InventoryUpdateResult,
    Severity,
    ValidationIssue,
    convert_records,
)
from .core.barcodes import ensure_unique_product_barcodes
from .core.mapping import merge_availability_into_description
from .core.normalize import make_handle, normalize_text, parse_quantity
from .io import read_diamond_file
from .io.detect import detect_encoding, sniff_dialect


_REQUIRED_WIX_EXPORT_COLUMNS = {"brand", "inventory", "sku"}
_EXCEL_QUOTED_FORMULA_PREFIX = '="'
_WIX_EXPORT_COLUMN_ALIASES = {
    "brand": "brand",
    "fieldtype": "fieldType",
    "inventory": "inventory",
    "plaindescription": "plainDescription",
    "sku": "sku",
}


@dataclass(frozen=True)
class _DiamondInventorySnapshot:
    inventory: str
    branches: tuple[str, ...]


def _canonical_wix_export_header(value: str | None) -> str:
    cleaned = normalize_text(value).lstrip("\ufeff")
    return _WIX_EXPORT_COLUMN_ALIASES.get(cleaned.casefold(), cleaned)


def _read_wix_export_rows(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    file_path = Path(path)
    raw_bytes = file_path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")

    dialect = sniff_dialect(text[:4096], delimiters=",;\t")
    reader = csv.DictReader(StringIO(text), dialect=dialect)
    header = [_canonical_wix_export_header(field) for field in (reader.fieldnames or [])]
    if not header:
        raise ValueError(f"Wix export CSV is empty: {file_path}")

    missing = sorted(column for column in _REQUIRED_WIX_EXPORT_COLUMNS if column not in header)
    if missing:
        raise ValueError(f"Wix export CSV is missing required columns: {', '.join(missing)}")

    reader.fieldnames = header

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {
            column: (raw_row.get(column, "") or "")
            for column in header
        }
        rows.append(row)

    return header, rows


def _inventory_match_key(value: str | None) -> str:
    """Normalize SKU/article number formatting for matching only."""
    text = normalize_text(value)
    if text.startswith(_EXCEL_QUOTED_FORMULA_PREFIX) and text.endswith('"'):
        text = normalize_text(text[2:-1])
    if text.startswith("'"):
        text = normalize_text(text[1:])
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _is_wix_product_row(row: Mapping[str, str]) -> bool:
    field_type = normalize_text(row.get("fieldType")).upper()
    return not field_type or field_type == "PRODUCT"


def _wix_brand_key(row: Mapping[str, str]) -> str:
    return normalize_brand_key(row.get("brand"))


def _is_managed_wix_product_row(
    row: Mapping[str, str],
    known_brands: Mapping[str, str],
) -> bool:
    return _is_wix_product_row(row) and _wix_brand_key(row) in known_brands


def _configured_brand_map(configured_brands: Sequence[str] | None) -> dict[str, str]:
    brands = dedupe_brands(configured_brands if configured_brands is not None else load_brands())
    if not brands:
        raise ValueError("Die Markenliste darf nicht leer sein.")
    return {normalize_brand_key(brand): brand for brand in brands}


def _make_issue_row(
    *,
    source_row: int,
    source: Mapping[str, str],
    field: str,
    severity: Severity,
    message: str,
    kind: str,
) -> InventoryUpdateIssueRow:
    return InventoryUpdateIssueRow(
        source_row=source_row,
        source=dict(source),
        kind=kind,
        issues=[
            ValidationIssue(
                source_row=source_row,
                field=field,
                severity=severity,
                message=message,
            )
        ],
    )


def _missing_brand_issue_rows(
    *,
    source_label: str,
    field: str,
    present_brand_keys: set[str],
    known_brands: Mapping[str, str],
) -> list[InventoryUpdateIssueRow]:
    rows: list[InventoryUpdateIssueRow] = []
    for brand_key, brand in known_brands.items():
        if brand_key in present_brand_keys:
            continue
        rows.append(
            _make_issue_row(
                source_row=0,
                source={"Datei": source_label, "Marke": brand},
                field=field,
                severity=Severity.ERROR,
                message=f"{source_label} enthält keine Produktzeile für Marke '{brand}'.",
                kind="safety",
            )
        )
    return rows


def _validate_wix_brands(
    rows: Sequence[Mapping[str, str]],
    known_brands: Mapping[str, str],
) -> list[InventoryUpdateIssueRow]:
    issues: list[InventoryUpdateIssueRow] = []
    present_brand_keys: set[str] = set()

    for row in rows:
        if not _is_wix_product_row(row):
            continue

        brand_key = _wix_brand_key(row)
        if brand_key in known_brands:
            present_brand_keys.add(brand_key)

    issues.extend(
        _missing_brand_issue_rows(
            source_label="Wix-Export",
            field="brand",
            present_brand_keys=present_brand_keys,
            known_brands=known_brands,
        )
    )
    return issues


def _validate_diamond_brands(
    records: Sequence[DiamondRecord],
    known_brands: Mapping[str, str],
) -> list[InventoryUpdateIssueRow]:
    issues: list[InventoryUpdateIssueRow] = []
    present_brand_keys: set[str] = set()

    for record in records:
        brand = normalize_text(record.data.get("Marke"))
        brand_key = normalize_brand_key(brand)
        if not brand:
            issues.append(
                _make_issue_row(
                    source_row=record.source_row,
                    source=record.data,
                    field="Marke",
                    severity=Severity.ERROR,
                    message="DIAMOND-Zeile hat keine Marke.",
                    kind="safety",
                )
            )
            continue
        if brand_key not in known_brands:
            issues.append(
                _make_issue_row(
                    source_row=record.source_row,
                    source=record.data,
                    field="Marke",
                    severity=Severity.ERROR,
                    message=f"DIAMOND-Export enthält eine unbekannte Marke: '{brand}'.",
                    kind="safety",
                )
            )
            continue

        present_brand_keys.add(brand_key)

    issues.extend(
        _missing_brand_issue_rows(
            source_label="DIAMOND-Export",
            field="Marke",
            present_brand_keys=present_brand_keys,
            known_brands=known_brands,
        )
    )
    return issues


def _managed_diamond_records(
    records: Sequence[DiamondRecord],
    known_brands: Mapping[str, str],
) -> list[DiamondRecord]:
    return [
        record
        for record in records
        if normalize_brand_key(record.data.get("Marke")) in known_brands
    ]


def _inventory_by_artikel_nr(
    records: Sequence[DiamondRecord],
) -> dict[str, _DiamondInventorySnapshot]:
    inventory: dict[str, int] = {}
    branches_by_artikel_nr: dict[str, list[str]] = {}

    for record in records:
        artikel_nr = _inventory_match_key(record.data.get("Artikel Nr"))
        if not artikel_nr:
            continue

        try:
            qty = parse_quantity(record.data.get("Menge"))
        except ValueError as exc:
            raise ValueError(
                f"Ungültige Menge in Lagerdatei bei Artikel Nr '{artikel_nr}' (Zeile {record.source_row})."
            ) from exc

        quantity = qty or 0
        inventory[artikel_nr] = inventory.get(artikel_nr, 0) + quantity
        if quantity > 0:
            branch = normalize_text(record.data.get("Filiale"))
            if branch:
                current = branches_by_artikel_nr.setdefault(artikel_nr, [])
                if branch not in current:
                    current.append(branch)

    return {
        artikel_nr: _DiamondInventorySnapshot(
            inventory=str(max(quantity, 0)),
            branches=tuple(branches_by_artikel_nr.get(artikel_nr, [])),
        )
        for artikel_nr, quantity in inventory.items()
    }


def _records_missing_from_wix(
    records: Sequence[DiamondRecord],
    wix_product_skus: set[str],
) -> list[DiamondRecord]:
    missing_records: list[DiamondRecord] = []

    for record in records:
        artikel_nr = _inventory_match_key(record.data.get("Artikel Nr"))
        if not artikel_nr:
            continue
        if artikel_nr in wix_product_skus:
            continue
        missing_records.append(record)

    return missing_records


def _missing_article_issue_rows(records: Sequence[DiamondRecord]) -> list[InventoryUpdateIssueRow]:
    rows: list[InventoryUpdateIssueRow] = []
    for record in records:
        if _inventory_match_key(record.data.get("Artikel Nr")):
            continue
        rows.append(
            _make_issue_row(
                source_row=record.source_row,
                source=record.data,
                field="Artikel Nr",
                severity=Severity.WARNING,
                message="DIAMOND-Zeile hat keine Artikelnummer und wurde nicht zugeordnet.",
                kind="unmatched_diamond",
            )
        )
    return rows


def _issue_rows_from_new_product_conversion(
    conversion_results,
) -> list[InventoryUpdateIssueRow]:
    issue_rows: list[InventoryUpdateIssueRow] = []
    for result in conversion_results:
        if not result.issues:
            continue
        issue_rows.append(
            InventoryUpdateIssueRow(
                source_row=result.source_row,
                source=dict(result.source),
                issues=list(result.issues),
                kind="new_product",
            )
        )
    return issue_rows


def _name_slug(value: str | None) -> str:
    return make_handle(value, prefix="")


def _unique_name_candidate(row: Mapping[str, str], source_row: int) -> str:
    name = normalize_text(row.get("name"))
    sku = normalize_text(row.get("sku"))
    handle = normalize_text(row.get("handle"))

    for suffix in (sku, handle, str(source_row)):
        if not suffix:
            continue
        candidate = f"{name} {suffix}" if name else suffix
        if candidate != name:
            return candidate
    return name


def _ensure_new_product_names_have_unique_slugs(
    new_results: Sequence[InventoryUpdateResult],
    existing_rows: Sequence[Mapping[str, str]],
) -> None:
    """Avoid Wix duplicate slug errors for generated update products.

    Wix derives product slugs during CSV import, but the product export does not
    expose a slug column. For new products only, make colliding names unique by
    appending the SKU so Wix can derive a unique slug.
    """

    used_slugs = {
        slug
        for row in existing_rows
        for slug in [_name_slug(row.get("name"))]
        if slug
    }

    for result in new_results:
        row = result.wix_row
        current_name = normalize_text(row.get("name"))
        current_slug = _name_slug(current_name)
        if not current_slug:
            continue
        if current_slug not in used_slugs:
            used_slugs.add(current_slug)
            continue

        candidate = _unique_name_candidate(row, result.source_row)
        candidate_slug = _name_slug(candidate)
        if candidate_slug in used_slugs:
            candidate = f"{candidate} {result.source_row}"
            candidate_slug = _name_slug(candidate)
        row["name"] = candidate
        used_slugs.add(candidate_slug)


def build_inventory_update_batch(
    *,
    wix_export_csv: str | Path,
    diamond_csv: str | Path,
    brands: Sequence[str] | None = None,
    options: ConversionOptions | None = None,
) -> InventoryUpdateBatch:
    """Update Wix export inventory from a DIAMOND inventory export."""

    known_brands = _configured_brand_map(brands)
    diamond_records = read_diamond_file(diamond_csv)
    if not diamond_records:
        raise ValueError(
            "Die Lagerdatei enthält keine erkennbaren Artikelnummern mit Mengen. "
            "Bitte prüfe, ob es ein DIAMOND CSV-Export ist."
        )

    header, rows = _read_wix_export_rows(wix_export_csv)

    issue_rows: list[InventoryUpdateIssueRow] = []
    issue_rows.extend(_validate_wix_brands(rows, known_brands))
    issue_rows.extend(_validate_diamond_brands(diamond_records, known_brands))
    managed_diamond_records = _managed_diamond_records(diamond_records, known_brands)

    inventory_by_sku = _inventory_by_artikel_nr(managed_diamond_records)
    if not inventory_by_sku and not issue_rows:
        raise ValueError(
            "Die Lagerdatei enthält keine erkennbaren Artikelnummern mit Mengen. "
            "Bitte prüfe, ob es ein DIAMOND CSV-Export ist."
        )

    wix_product_skus = {
        sku
        for row in rows
        if _is_managed_wix_product_row(row, known_brands)
        for sku in [_inventory_match_key(row.get("sku"))]
        if sku
    }
    issue_rows.extend(_missing_article_issue_rows(managed_diamond_records))
    new_product_records = _records_missing_from_wix(
        managed_diamond_records,
        wix_product_skus,
    )
    new_product_batch = convert_records(
        records=new_product_records,
        template_header=header,
        options=options or ConversionOptions(),
    )
    issue_rows.extend(_issue_rows_from_new_product_conversion(new_product_batch.results))

    updated_rows: list[dict[str, str]] = []
    existing_results: list[InventoryUpdateResult] = []

    for source_row, original_row in enumerate(rows, start=2):
        row = dict(original_row)
        is_product = _is_wix_product_row(row)
        is_managed_product = _is_managed_wix_product_row(row, known_brands)
        sku = _inventory_match_key(row.get("sku"))
        old_inventory = normalize_text(row.get("inventory"))
        matched = bool(is_managed_product and sku and sku in inventory_by_sku)
        snapshot = inventory_by_sku.get(sku)
        new_inventory = old_inventory
        old_description = row.get("plainDescription", "")
        new_description = old_description
        set_to_zero = False

        if is_managed_product:
            if matched and snapshot is not None:
                new_inventory = snapshot.inventory
            else:
                new_inventory = "0"
                set_to_zero = True
            row["inventory"] = new_inventory
            if "plainDescription" in row:
                branches = snapshot.branches if matched and snapshot is not None else ()
                new_description = merge_availability_into_description(
                    old_description,
                    branches,
                )
                row["plainDescription"] = new_description

        updated_rows.append(row)

        if is_product:
            source_kind = "wix" if is_managed_product else "wix_unmanaged"
            existing_results.append(
                InventoryUpdateResult(
                    source_row=source_row,
                    wix_row=row,
                    original_inventory=old_inventory,
                    updated_inventory=new_inventory,
                    matched=matched,
                    changed=(
                        new_inventory != old_inventory
                        or new_description != old_description
                    ),
                    set_to_zero=set_to_zero,
                    source_kind=source_kind,
                )
            )

    existing_barcodes = [
        normalize_text(row.get("barcode"))
        for row in updated_rows
        if normalize_text(row.get("barcode"))
    ]
    new_results: list[InventoryUpdateResult] = []
    for result in new_product_batch.results:
        if result.has_errors:
            continue

        row = dict(result.wix_row)
        sku = _inventory_match_key(row.get("sku"))
        snapshot = inventory_by_sku.get(sku)
        if "plainDescription" in row:
            row["plainDescription"] = merge_availability_into_description(
                row.get("plainDescription", ""),
                snapshot.branches if snapshot is not None else (),
            )
        inventory = normalize_text(row.get("inventory"))
        new_results.append(
            InventoryUpdateResult(
                source_row=result.source_row,
                wix_row=row,
                original_inventory="",
                updated_inventory=inventory,
                matched=False,
                changed=True,
                set_to_zero=False,
                is_new_product=True,
                source_kind="diamond",
            )
        )

    ensure_unique_product_barcodes(
        [(result.source_row, result.wix_row) for result in new_results],
        reserved_barcodes=existing_barcodes,
    )
    _ensure_new_product_names_have_unique_slugs(
        new_results,
        updated_rows,
    )
    updated_rows.extend(result.wix_row for result in new_results)

    return InventoryUpdateBatch(
        header=header,
        rows=updated_rows,
        results=[*new_results, *existing_results],
        issue_rows=issue_rows,
    )
