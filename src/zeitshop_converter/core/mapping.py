from __future__ import annotations

from collections.abc import MutableMapping, Sequence
import re

from .models import ConversionOptions, DiamondRecord, Severity, ValidationIssue
from .normalize import (
    format_decimal,
    make_handle,
    normalize_inventory,
    normalize_text,
    parse_decimal,
    parse_quantity,
)

_WORD_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
_AM_BOGEN_AVAILABILITY = "Verfügbar in der Bijouterie am Bogen in Bremgarten AG"
_DROZ_AVAILABILITY = "Verfügbar in der Bijouterie Droz in Zofingen AG"
_BOTH_BRANCHES_AVAILABILITY = (
    "Verfügbar in der Bijouterie am Bogen in Bremgarten AG "
    "und in der Bijouterie Droz in Zofingen AG"
)
_LOCATION_CATEGORY_SLUGS = (
    ("Am Bogen", "bremgarten"),
    ("Droz", "zofingen"),
)
_MANAGED_LOCATION_CATEGORY_SLUGS = frozenset(
    slug for _, slug in _LOCATION_CATEGORY_SLUGS
)
_SCOPED_LOCATION_CATEGORY_SLUGS = {
    "uhren": {
        "bremgarten": "bremgarten-uhren",
        "zofingen": "zofingen-uhren",
    },
    "schmuck": {
        "bremgarten": "bremgarten-schmuck",
        "zofingen": "zofingen-schmuck",
    },
}
_MANAGED_SCOPED_LOCATION_CATEGORY_SLUGS = frozenset(
    scoped_slug
    for scoped_slugs in _SCOPED_LOCATION_CATEGORY_SLUGS.values()
    for scoped_slug in scoped_slugs.values()
)
_SCOPED_BRAND_CATEGORY_SLUGS = {
    "thomas sabo": {
        "uhren": "thomas-sabo-uhren",
        "schmuck": "thomas-sabo",
    },
}
_KNOWN_AVAILABILITY_SENTENCES = (
    _AM_BOGEN_AVAILABILITY,
    _DROZ_AVAILABILITY,
    _BOTH_BRANCHES_AVAILABILITY,
    "Verfügbar in dem Ladengeschäft Bijouterie am Bogen in Bremgarten AG",
    "Verfügbar in dem Ladengeschäft Bijouterie Droz in Zofingen AG",
    (
        "Verfügbar in den Ladengeschäften Bijouterie Am Bogen in Bremgarten AG "
        "und in der Bijouterie Droz in Zofingen AG"
    ),
)
_HTML_CLOSING_PARAGRAPH_RE = re.compile(
    r"(?P<closing>\s*</p>\s*)$", flags=re.IGNORECASE
)
_HTML_BREAK_TAIL_RE = re.compile(r"(?P<br>\s*<br\s*/?>\s*)$", flags=re.IGNORECASE)


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
    if record.source_format == "lager_csv":
        items: list[str] = []
        referenz = normalize_text(record.data.get("Referenz"))
        if referenz:
            items.append(f"Referenz: {referenz}")

        branch_names = _available_branches(record)
        availability = availability_sentence_from_branches(branch_names)
        if availability:
            items.append(availability)
        return "\n".join(items)

    items: list[str] = []
    warengruppe = _normalize_category_text(record.data.get("Warengruppe"))
    kategorie = normalize_text(record.data.get("Kategorie"))

    if warengruppe:
        items.append(f"Warengruppe: {warengruppe}")
    if kategorie:
        items.append(f"Kategorie: {kategorie}")

    return " | ".join(items)


def _normalize_category_text(value: str | None) -> str:
    """Canonicalize mixed-category labels before display or slug mapping."""
    text = normalize_text(value)
    if not text:
        return ""

    compact = (
        text.casefold()
        .replace(" ", "")
        .replace("-", "")
        .replace("/", "")
        .replace("&", "")
        .replace("und", "")
    )
    if compact == "collier":
        return "Colliers"
    if compact == "ring":
        return "Ringe"
    if text.casefold().endswith("uhr"):
        return f"{text}en"
    return text


def _category_slugs_for_value(value: str | None) -> list[str]:
    """Expand one DIAMOND category value into one or more Wix category slugs."""
    text = normalize_text(value)
    if not text:
        return []

    compact = (
        text.casefold()
        .replace(" ", "")
        .replace("-", "")
        .replace("/", "")
        .replace("&", "")
        .replace("und", "")
    )
    if compact in {"herrendamenuhr", "herrendamen"}:
        return ["herrenuhren", "damenuhren"]

    slug = make_handle(_normalize_category_text(text), prefix="")
    if slug == "armbanduhren":
        return []
    return [slug] if slug else []


def _brand_category_slug(
    value: str | None,
    broad_category_slug: str = "",
) -> str:
    """Build the globally unique brand slug for a Wix category branch."""
    brand = normalize_text(value)
    if not brand:
        return ""

    scoped_slugs = _SCOPED_BRAND_CATEGORY_SLUGS.get(brand.casefold(), {})
    scoped_slug = scoped_slugs.get(broad_category_slug)
    if scoped_slug:
        return scoped_slug
    if brand == "Eichmüller":
        return "eichmüller"
    return make_handle(brand, prefix="")


def merge_scoped_brand_category_slug(
    category_slugs: str | None,
    brand: str | None,
    category: str | None,
) -> str:
    """Reconcile brand slugs whose Wix category depends on their parent branch."""
    current = category_slugs or ""
    scoped_slugs = _SCOPED_BRAND_CATEGORY_SLUGS.get(
        normalize_text(brand).casefold()
    )
    broad_slugs = _category_slugs_for_value(category)
    broad = broad_slugs[0] if broad_slugs else ""
    if not scoped_slugs or broad not in scoped_slugs:
        return current

    expected = scoped_slugs[broad]
    managed = frozenset(slug.casefold() for slug in scoped_slugs.values())
    reconciled: list[str] = []
    found_expected = False

    for raw_slug in current.split(";"):
        slug = normalize_text(raw_slug)
        if not slug:
            continue

        slug_key = slug.casefold()
        if slug_key not in managed:
            reconciled.append(slug)
            continue
        if slug_key == expected.casefold() and not found_expected:
            reconciled.append(expected)
            found_expected = True

    if not found_expected:
        reconciled.append(expected)
    return ";".join(reconciled)


def availability_sentence_from_branches(branches: Sequence[str]) -> str:
    """Build the storefront availability sentence from current branch stock."""
    seen = _branch_keys(branches)

    if seen == {"Am Bogen"}:
        return _AM_BOGEN_AVAILABILITY
    if seen == {"Droz"}:
        return _DROZ_AVAILABILITY
    if seen == {"Am Bogen", "Droz"}:
        return _BOTH_BRANCHES_AVAILABILITY
    return ""


def _branch_keys(branches: Sequence[str]) -> set[str]:
    """Map branch labels to the storefront locations they represent."""
    seen: set[str] = set()
    for raw_branch in branches:
        for branch_part in raw_branch.split("|"):
            branch = _branch_key(branch_part)
            if branch:
                seen.add(branch)
    return seen


def location_category_slugs_from_branches(branches: Sequence[str]) -> tuple[str, ...]:
    """Return Wix location slugs using the availability branch mapping."""
    branch_keys = _branch_keys(branches)
    return tuple(
        slug
        for branch, slug in _LOCATION_CATEGORY_SLUGS
        if branch in branch_keys
    )


def scoped_location_category_slugs_from_branches(
    branches: Sequence[str],
    broad_category_slug: str,
) -> tuple[str, ...]:
    """Return the location slugs belonging below a broad Wix category."""
    scoped_slugs = _SCOPED_LOCATION_CATEGORY_SLUGS.get(broad_category_slug, {})
    return tuple(
        scoped_slugs[location_slug]
        for location_slug in location_category_slugs_from_branches(branches)
        if location_slug in scoped_slugs
    )


def merge_location_category_slugs(
    category_slugs: str | None,
    branches: Sequence[str],
    category: str | None = None,
) -> str:
    """Replace managed location slugs while preserving all other categories."""
    managed_slugs = (
        _MANAGED_LOCATION_CATEGORY_SLUGS
        | _MANAGED_SCOPED_LOCATION_CATEGORY_SLUGS
    )
    existing: list[str] = []
    for raw_slug in (category_slugs or "").split(";"):
        slug = normalize_text(raw_slug)
        if slug and slug.casefold() not in managed_slugs:
            existing.append(slug)

    broad_slugs = _category_slugs_for_value(category)
    broad = next(
        (slug for slug in broad_slugs if slug in _SCOPED_LOCATION_CATEGORY_SLUGS),
        "",
    )
    if not broad:
        for raw_slug in (category_slugs or "").split(";"):
            candidate = normalize_text(raw_slug).casefold()
            if candidate in _SCOPED_LOCATION_CATEGORY_SLUGS:
                broad = candidate
                break

    location_slugs = location_category_slugs_from_branches(branches)
    scoped_slugs = scoped_location_category_slugs_from_branches(branches, broad)
    return ";".join([*existing, *location_slugs, *scoped_slugs])


def _branch_key(value: str | None) -> str:
    """Map DIAMOND branch labels to the two storefront availability locations."""
    branch = normalize_text(value).casefold()
    if "bogen" in branch:
        return "Am Bogen"
    if "droz" in branch:
        return "Droz"
    return ""


def _available_branches(record: DiamondRecord) -> list[str]:
    """Return branches only when the source row represents positive stock."""
    try:
        quantity = parse_quantity(record.data.get("Menge"))
    except ValueError:
        return []
    if not quantity or quantity <= 0:
        return []
    return [
        normalize_text(part)
        for part in record.data.get("Filiale", "").split("|")
        if normalize_text(part)
    ]


def _remove_availability_tail(text: str) -> str:
    """Remove any known availability sentence at the end of a description."""
    base = text.rstrip()
    changed = True
    while changed:
        changed = False
        for sentence in _KNOWN_AVAILABILITY_SENTENCES:
            if base.casefold() == sentence.casefold():
                base = ""
                changed = True
                break

            pattern = re.compile(
                rf"(?is)(?:\s*(?:<br\s*/?>|\||\n)\s*)?{re.escape(sentence)}\s*$"
            )
            updated = pattern.sub("", base).rstrip()
            if updated != base:
                base = updated
                changed = True
                break
    return base


def merge_availability_into_description(description: str | None, branches: Sequence[str]) -> str:
    """Replace the availability tail in a Wix description while preserving prior text."""
    text = (description or "").strip()
    base = text
    html_closing = ""

    closing_match = _HTML_CLOSING_PARAGRAPH_RE.search(base)
    if closing_match is not None:
        html_closing = closing_match.group("closing")
        base = base[: closing_match.start()].rstrip()

    base = _remove_availability_tail(base)
    base = _HTML_BREAK_TAIL_RE.sub("", base).rstrip()

    if html_closing:
        availability = availability_sentence_from_branches(branches)
        if base and availability:
            return f"{base}<br>{availability}{html_closing}"
        return f"{availability}{html_closing}" if availability else f"{base}{html_closing}"

    availability = availability_sentence_from_branches(branches)
    if base and availability:
        if re.search(r"<br\s*/?>\s*$", base, flags=re.IGNORECASE):
            return f"{base}{availability}"
        if "<br" in base.casefold():
            return f"{base}<br>{availability}"
        return f"{base}\n{availability}"

    return availability or base


def _build_category_slugs(record: DiamondRecord) -> tuple[str, str]:
    """Build Wix category slug fields from DIAMOND category values."""
    broad_slugs = _category_slugs_for_value(record.data.get("Kategorie"))
    broad = broad_slugs[0] if broad_slugs else ""
    fine_slugs = _category_slugs_for_value(record.data.get("Warengruppe"))
    brand = _brand_category_slug(record.data.get("Marke"), broad)

    slugs: list[str] = []
    for slug in [*broad_slugs, *fine_slugs, brand]:
        if slug and slug not in slugs:
            slugs.append(slug)

    branches = _available_branches(record)
    for slug in [
        *location_category_slugs_from_branches(branches),
        *scoped_location_category_slugs_from_branches(branches, broad),
    ]:
        if slug not in slugs:
            slugs.append(slug)

    return broad, ";".join(slugs)


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

    base_handle_seed = article_nr or str(record.source_row)
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
    description = _build_plain_description(record)
    row["plainDescription"] = description
    if "Beschreibung" in row:
        row["Beschreibung"] = description
    primary_category_slug, category_slugs = _build_category_slugs(record)
    if "primaryCategorySlug" in row:
        row["primaryCategorySlug"] = primary_category_slug
    if "categorySlugs" in row:
        row["categorySlugs"] = category_slugs
    row["sku"] = article_nr
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
