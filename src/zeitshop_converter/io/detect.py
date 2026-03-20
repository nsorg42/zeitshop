from __future__ import annotations

import csv
import importlib
from typing import Callable


def _load_charset_normalizer() -> Callable[[bytes], object] | None:
    """Load charset-normalizer lazily so static analyzers stay quiet.

    Pylance can flag optional imports as missing when VS Code uses a different
    interpreter than the project's virtual environment. A runtime import keeps
    fallback behavior and avoids false-positive import warnings in the module.
    """
    try:
        module = importlib.import_module("charset_normalizer")
    except ImportError:  # pragma: no cover - dependency is declared in pyproject
        return None

    loaded = getattr(module, "from_bytes", None)
    if callable(loaded):
        return loaded
    return None


from_bytes = _load_charset_normalizer()


class SemicolonDialect(csv.excel):
    """Fallback CSV dialect used when sniffing fails."""

    delimiter = ";"


def detect_encoding(raw_bytes: bytes) -> str:
    """Best-effort encoding detection for unknown CSV byte streams."""

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            raw_bytes.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue

    if from_bytes is not None:
        best = from_bytes(raw_bytes).best()
        if best is not None and best.encoding:
            return best.encoding

    return "latin1"


def sniff_dialect(sample_text: str, delimiters: str = ";,\t") -> csv.Dialect:
    """Infer delimiter style from a text sample using csv.Sniffer."""
    if not sample_text.strip():
        return SemicolonDialect()

    sniffer = csv.Sniffer()
    try:
        return sniffer.sniff(sample_text, delimiters=delimiters)
    except csv.Error:
        return SemicolonDialect()
