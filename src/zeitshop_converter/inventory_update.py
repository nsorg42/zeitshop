from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from .core import InventoryUpdateBatch, InventoryUpdateResult
from .core.normalize import normalize_text, parse_quantity
from .io import read_diamond_file
from .io.detect import detect_encoding


_REQUIRED_WIX_EXPORT_COLUMNS = {"inventory", "sku"}


def _read_wix_export_rows(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    file_path = Path(path)
    raw_bytes = file_path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")

    reader = csv.DictReader(StringIO(text), delimiter=",")
    header = [field.lstrip("\ufeff").strip() for field in (reader.fieldnames or [])]
    if not header:
        raise ValueError(f"Wix export CSV is empty: {file_path}")

    missing = sorted(column for column in _REQUIRED_WIX_EXPORT_COLUMNS if column not in header)
    if missing:
        raise ValueError(f"Wix export CSV is missing required columns: {', '.join(missing)}")

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {
            column: (raw_row.get(column, "") or "")
            for column in header
        }
        rows.append(row)

    return header, rows


def _inventory_by_artikel_nr(diamond_csv: str | Path) -> dict[str, str]:
    inventory: dict[str, int] = {}
    for record in read_diamond_file(diamond_csv):
        artikel_nr = normalize_text(record.data.get("Artikel Nr"))
        if not artikel_nr:
            continue

        try:
            qty = parse_quantity(record.data.get("Menge"))
        except ValueError as exc:
            raise ValueError(
                f"Ungültige Menge in Lagerdatei bei Artikel Nr '{artikel_nr}' (Zeile {record.source_row})."
            ) from exc

        inventory[artikel_nr] = inventory.get(artikel_nr, 0) + (qty or 0)

    return {artikel_nr: str(max(quantity, 0)) for artikel_nr, quantity in inventory.items()}


def build_inventory_update_batch(
    *,
    wix_export_csv: str | Path,
    diamond_csv: str | Path,
) -> InventoryUpdateBatch:
    """Update Wix export inventory from a DIAMOND lager.csv export."""

    inventory_by_sku = _inventory_by_artikel_nr(diamond_csv)
    header, rows = _read_wix_export_rows(wix_export_csv)

    updated_rows: list[dict[str, str]] = []
    results: list[InventoryUpdateResult] = []

    for source_row, original_row in enumerate(rows, start=2):
        row = dict(original_row)
        field_type = normalize_text(row.get("fieldType")).upper()
        sku = normalize_text(row.get("sku"))
        old_inventory = normalize_text(row.get("inventory"))
        is_product = not field_type or field_type == "PRODUCT"
        matched = bool(is_product and sku and sku in inventory_by_sku)
        new_inventory = inventory_by_sku.get(sku, old_inventory) if matched else old_inventory

        if matched:
            row["inventory"] = new_inventory

        updated_rows.append(row)

        if is_product:
            results.append(
                InventoryUpdateResult(
                    source_row=source_row,
                    wix_row=row,
                    original_inventory=old_inventory,
                    updated_inventory=new_inventory,
                    matched=matched,
                    changed=matched and new_inventory != old_inventory,
                )
            )

    return InventoryUpdateBatch(header=header, rows=updated_rows, results=results)
