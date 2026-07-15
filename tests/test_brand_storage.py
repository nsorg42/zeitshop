from pathlib import Path

import pytest

from zeitshop_converter.brand_storage import (
    default_brands,
    load_brands,
    reset_brands_to_default,
    save_brands,
)


def test_load_brands_creates_default_file(tmp_path: Path) -> None:
    brand_path = tmp_path / "brands.txt"

    brands = load_brands(brand_path)

    assert brands == [
        "Aerowatch",
        "Certina",
        "Hamilton",
        "ICE Watch",
        "Maurice Lacroix",
        "Rado",
        "Thomas Sabo",
        "Ti Sento",
        "Tissot",
    ]
    assert brand_path.read_text(encoding="utf-8").splitlines() == brands


def test_save_brands_deduplicates_and_ignores_empty_lines(tmp_path: Path) -> None:
    brand_path = tmp_path / "brands.txt"

    saved = save_brands([" Brand ", "", "brand", "Other"], brand_path)

    assert saved == ["Brand", "Other"]
    assert load_brands(brand_path) == ["Brand", "Other"]


def test_reset_brands_to_default_replaces_runtime_file(tmp_path: Path) -> None:
    brand_path = tmp_path / "brands.txt"
    save_brands(["Custom"], brand_path)

    reset = reset_brands_to_default(brand_path)

    assert reset == default_brands()
    assert load_brands(brand_path) == default_brands()


def test_save_brands_rejects_empty_list(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Markenliste"):
        save_brands(["", "  "], tmp_path / "brands.txt")
