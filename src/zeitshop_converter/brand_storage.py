from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Iterable

from .core.normalize import normalize_text

DEFAULT_BRANDS = (
    "Aerowatch",
    "Certina",
    "Hamilton",
    "ICE Watch",
    "Maurice Lacroix",
    "Rado",
    "Thomas Sabo",
    "Ti Sento",
    "Tissot",
)
BRAND_STORAGE_PATH = Path.home() / ".zeitshop_converter" / "brands.txt"


def normalize_brand_key(value: str | None) -> str:
    """Normalize a brand for comparisons while preserving display names elsewhere."""
    return normalize_text(value).casefold()


def dedupe_brands(brands: Iterable[str]) -> list[str]:
    """Normalize and deduplicate brand names while preserving first display spelling."""
    result: list[str] = []
    seen: set[str] = set()
    for raw_brand in brands:
        brand = normalize_text(raw_brand)
        key = normalize_brand_key(brand)
        if not brand or key in seen:
            continue
        seen.add(key)
        result.append(brand)
    return result


def default_brands() -> list[str]:
    """Load the packaged default brands, falling back to the compiled defaults."""
    try:
        text = (
            resources.files("zeitshop_converter")
            .joinpath("data/default_brands.txt")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return list(DEFAULT_BRANDS)

    brands = dedupe_brands(text.splitlines())
    return brands or list(DEFAULT_BRANDS)


def save_brands(brands: Iterable[str], path: str | Path | None = None) -> list[str]:
    """Persist the configured brand list and return the normalized saved values."""
    normalized = dedupe_brands(brands)
    if not normalized:
        raise ValueError("Die Markenliste darf nicht leer sein.")

    target = Path(path) if path is not None else BRAND_STORAGE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(normalized) + "\n", encoding="utf-8")
    return normalized


def load_brands(path: str | Path | None = None) -> list[str]:
    """Read the runtime brand list, creating it from defaults when missing."""
    target = Path(path) if path is not None else BRAND_STORAGE_PATH
    if not target.exists():
        return save_brands(default_brands(), target)

    brands = dedupe_brands(target.read_text(encoding="utf-8").splitlines())
    if not brands:
        raise ValueError("Die gespeicherte Markenliste ist leer.")
    return brands


def reset_brands_to_default(path: str | Path | None = None) -> list[str]:
    """Replace the runtime brand list with the packaged defaults."""
    return save_brands(default_brands(), path)
