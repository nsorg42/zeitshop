from __future__ import annotations

import csv

try:
    from charset_normalizer import from_bytes
except ImportError:  # pragma: no cover - dependency is declared in pyproject
    from_bytes = None


class SemicolonDialect(csv.excel):
    delimiter = ";"


def detect_encoding(raw_bytes: bytes) -> str:
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
    if not sample_text.strip():
        return SemicolonDialect()

    sniffer = csv.Sniffer()
    try:
        return sniffer.sniff(sample_text, delimiters=delimiters)
    except csv.Error:
        return SemicolonDialect()
