from __future__ import annotations

from collections import Counter
from collections.abc import MutableMapping, Sequence

from .normalize import normalize_text

_MAX_WIX_BARCODE_LENGTH = 40


def _trim_with_suffix(base: str, suffix: str) -> str:
    """Build a bounded barcode candidate that always keeps the suffix."""
    clean_base = normalize_text(base)
    clean_suffix = normalize_text(suffix)
    if not clean_suffix:
        return clean_base[:_MAX_WIX_BARCODE_LENGTH]
    if len(clean_suffix) >= _MAX_WIX_BARCODE_LENGTH:
        return clean_suffix[:_MAX_WIX_BARCODE_LENGTH]

    head_limit = _MAX_WIX_BARCODE_LENGTH - len(clean_suffix) - 1
    head = clean_base[: max(head_limit, 0)].rstrip("-")
    if not head:
        return clean_suffix[:_MAX_WIX_BARCODE_LENGTH]
    return f"{head}-{clean_suffix}"


def _candidate_barcodes(
    *,
    barcode: str,
    sku: str,
    handle: str,
    source_row: int,
) -> list[str]:
    """Return deterministic fallback candidates for a conflicting barcode."""
    candidates: list[str] = []
    for candidate in (
        sku,
        handle,
        _trim_with_suffix(sku or handle or barcode or "zs", str(source_row)),
        f"zs-{source_row}",
    ):
        text = normalize_text(candidate)
        if not text:
            continue
        if len(text) > _MAX_WIX_BARCODE_LENGTH:
            text = text[:_MAX_WIX_BARCODE_LENGTH]
        if text and text not in candidates:
            candidates.append(text)
    return candidates


def ensure_unique_product_barcodes(
    products: Sequence[tuple[int, MutableMapping[str, str]]],
    reserved_barcodes: Sequence[str] = (),
) -> None:
    """Mutate PRODUCT rows so every non-empty barcode is unique.

    Rows that already have a unique barcode keep it. Rows inside a duplicate
    barcode group receive a deterministic fallback derived from SKU, handle,
    and source row. Reserved barcodes are treated as already used but are not
    mutated.
    """

    original_barcodes = [
        normalize_text(row.get("barcode"))
        for _source_row, row in products
    ]
    counts = Counter(barcode for barcode in original_barcodes if barcode)
    reserved_keys = {
        normalize_text(barcode).casefold()
        for barcode in reserved_barcodes
        if normalize_text(barcode)
    }
    used = set(reserved_keys)
    used.update(
        barcode.casefold()
        for barcode, count in counts.items()
        if count == 1
        and barcode.casefold() not in reserved_keys
    )

    for (source_row, row), original in zip(products, original_barcodes, strict=False):
        original_key = original.casefold()
        if not original:
            continue
        if counts[original] == 1 and original_key not in reserved_keys:
            continue

        sku = normalize_text(row.get("sku"))
        handle = normalize_text(row.get("handle"))

        for candidate in _candidate_barcodes(
            barcode=original,
            sku=sku,
            handle=handle,
            source_row=source_row,
        ):
            key = candidate.casefold()
            if key in used:
                continue
            row["barcode"] = candidate
            used.add(key)
            break
        else:  # pragma: no cover - defensive fallback
            row["barcode"] = ""
