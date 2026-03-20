from __future__ import annotations

from collections.abc import MutableMapping, Sequence
import re

from .models import ConversionOptions, DiamondRecord, Severity, ValidationIssue
from .normalize import format_decimal, make_handle, normalize_inventory, normalize_text, parse_decimal

_WORD_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


def _tokens_equal(left: str, right: str) -> bool:
    """Case-insensitive token comparison with simple plural handling."""
    a = left.casefold()
    b = right.casefold()
    if a == b:
        return True
    if a.endswith("s") and len(a) > 3 and a[:-1] == b:
        return True
    if b.endswith("s") and len(b) > 3 and b[:-1] == a:
        return True
    return False


def _dedupe_compound_repeat(token: str) -> str:
    """Fix merged repeats like 'OhrsteckerOhrstecker'."""
    raw = token.strip()
    if not raw:
        return ""

    lower = raw.casefold()
    length = len(raw)
    if length >= 8 and length % 2 == 0:
        half = length // 2
        if lower[:half] == lower[half:]:
            return raw[:half]
    return raw


def _extract_tokens(text: str) -> list[str]:
    """Extract clean word-like tokens and remove direct repetition."""
    # regex-based tokenization is more robust than split(" ") for punctuation,
    words = [_dedupe_compound_repeat(token) for token in _WORD_RE.findall(text)]

    result: list[str] = []
    for token in words:
        if not token:
            continue
        if result and _tokens_equal(result[-1], token):
            continue
        result.append(token)

    # Collapse patterns where the whole phrase is repeated:
    total = len(result)
    for size in range(1, total // 2 + 1):
        if total % size != 0:
            continue
        first = result[:size]
        repeats = total // size
        if repeats <= 1:
            continue
        if all(
            _tokens_equal(first[index], result[block * size + index])
            for block in range(1, repeats)
            for index in range(size)
        ):
            return first

    return result


def _drop_prefix_overlap(candidate: list[str], existing: list[str]) -> list[str]:
    """Drop candidate prefix that already exists at the end of current name."""

    max_overlap = min(len(candidate), len(existing))
    for overlap in range(max_overlap, 0, -1):
        prefix = candidate[:overlap]
        suffix = existing[-overlap:]
        if all(_tokens_equal(a, b) for a, b in zip(prefix, suffix, strict=False)):
            return candidate[overlap:]
    return candidate


def _build_name(record: DiamondRecord) -> tuple[str, bool]:
    """Build readable product names while avoiding duplicate words/phrases."""

    brand = normalize_text(record.data.get("Marke"))
    line = normalize_text(record.data.get("Produktlinie"))
    short = normalize_text(record.data.get("Kurzbeschreibung"))
    fallback = normalize_text(record.data.get("Artikel Nr"))

    name_tokens: list[str] = []
    for component in (brand, line, short):
        if not component:
            continue
        tokens = _extract_tokens(component)
        tokens = _drop_prefix_overlap(tokens, name_tokens)
        for token in tokens:
            if any(_tokens_equal(token, existing) for existing in name_tokens):
                continue
            name_tokens.append(token)

    if name_tokens:
        name = " ".join(name_tokens)
    else:
        fallback_tokens = _extract_tokens(fallback)
        name = " ".join(fallback_tokens) if fallback_tokens else f"product-{record.source_row}"

    if len(name) <= 80:
        return name, False

    return name[:80].rstrip(), True


def _build_plain_description(record: DiamondRecord) -> str:
    """Compose a simple human-readable description from optional source fields."""

    items: list[str] = []
    warengruppe = normalize_text(record.data.get("Warengruppe"))
    kategorie = normalize_text(record.data.get("Kategorie"))

    if warengruppe:
        items.append(f"Warengruppe: {warengruppe}")
    if kategorie:
        items.append(f"Kategorie: {kategorie}")

    return " | ".join(items)


def _dedupe_handle(base_handle: str, seen_handles: MutableMapping[str, int]) -> tuple[str, bool]:
    """Ensure generated handles are unique by appending -2, -3, ... when needed."""

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
    """Map one canonical DIAMOND record into one Wix PRODUCT row."""

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
    if "barcode" in row and referenz:
        row["barcode"] = referenz

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
