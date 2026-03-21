import csv
from types import SimpleNamespace

import pytest

from zeitshop_converter.io import detect


def test_load_charset_normalizer_returns_none_when_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(_name: str) -> object:
        raise ImportError("missing")

    monkeypatch.setattr(detect.importlib, "import_module", fake_import)

    assert detect._load_charset_normalizer() is None


def test_load_charset_normalizer_returns_none_when_from_bytes_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(detect.importlib, "import_module", lambda _name: SimpleNamespace())

    assert detect._load_charset_normalizer() is None


def test_load_charset_normalizer_returns_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    loader = lambda raw: raw
    monkeypatch.setattr(detect.importlib, "import_module", lambda _name: SimpleNamespace(from_bytes=loader))

    assert detect._load_charset_normalizer() is loader


def test_detect_encoding_prefers_utf8_sig() -> None:
    assert detect.detect_encoding("hello".encode("utf-8-sig")) == "utf-8-sig"


def test_detect_encoding_uses_charset_normalizer_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMatches:
        def best(self) -> object:
            return SimpleNamespace(encoding="koi8-r")

    monkeypatch.setattr(detect, "from_bytes", lambda raw: FakeMatches())

    assert detect.detect_encoding(bytes([0x81])) == "koi8-r"


def test_detect_encoding_falls_back_to_latin1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "from_bytes", None)

    assert detect.detect_encoding(bytes([0x81])) == "latin1"


def test_sniff_dialect_detects_comma_delimiter() -> None:
    dialect = detect.sniff_dialect("a,b,c\n1,2,3\n")
    assert dialect.delimiter == ","


def test_sniff_dialect_uses_semicolon_fallback_for_empty_or_invalid_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert detect.sniff_dialect("").delimiter == ";"

    def fake_sniff(self, sample_text: str, delimiters: str = ";,\t") -> csv.Dialect:
        raise csv.Error("bad sample")

    monkeypatch.setattr(csv.Sniffer, "sniff", fake_sniff)

    assert detect.sniff_dialect("not enough structure").delimiter == ";"
