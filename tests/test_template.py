from pathlib import Path

import pytest

from zeitshop_converter.io.wix_template import default_template_header, load_template_header


def test_default_template_header_is_available() -> None:
    header = default_template_header()
    assert len(header) == 91
    assert header[0] == "handle"
    assert "fieldType" in header
    assert "price" in header


def test_load_template_header_uses_built_in_template_when_path_is_missing() -> None:
    header = load_template_header()
    assert len(header) == 91
    assert header[0] == "handle"


def test_template_requires_mandatory_columns(tmp_path: Path) -> None:
    template = tmp_path / "template.csv"
    template.write_text("handle,name\nfoo,bar\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        load_template_header(template)


def test_load_template_header_strips_bom_and_whitespace(tmp_path: Path) -> None:
    template = tmp_path / "template.csv"
    template.write_text("\ufeffhandle, name , fieldType , visible , price , inventory , sku \n", encoding="utf-8")

    header = load_template_header(template)

    assert header == ["handle", "name", "fieldType", "visible", "price", "inventory", "sku"]


def test_load_template_header_rejects_empty_template(tmp_path: Path) -> None:
    template = tmp_path / "template.csv"
    template.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Template CSV is empty"):
        load_template_header(template)
