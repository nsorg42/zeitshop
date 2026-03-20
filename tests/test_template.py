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
