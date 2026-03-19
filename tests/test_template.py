from pathlib import Path

import pytest

from zeitshop_converter.io.wix_template import load_template_header


def test_template_requires_mandatory_columns(tmp_path: Path) -> None:
    template = tmp_path / "template.csv"
    template.write_text("handle,name\nfoo,bar\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        load_template_header(template)
