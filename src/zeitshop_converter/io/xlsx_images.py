from __future__ import annotations

import csv
import hashlib
import posixpath
from pathlib import Path, PurePosixPath
from typing import Sequence
import xml.etree.ElementTree as ET
import zipfile

from ..core.models import DiamondRecord


_XDR_NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
_PKG_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
_DRAWING_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
_OFFICE_REL_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def default_xlsx_image_export_dir(path: str | Path) -> Path:
    """Build a stable cache directory for extracted embedded XLSX images."""

    file_path = Path(path).expanduser().resolve()
    stat = file_path.stat()
    fingerprint = hashlib.sha1(
        f"{file_path}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:12]
    return Path.home() / ".zeitshop_converter" / "xlsx_images" / f"{file_path.stem}-{fingerprint}"


def resolve_xlsx_image_export_dir(path: str | Path, output_dir: str | Path | None = None) -> Path:
    """Resolve explicit export directory or fall back to the stable cache path."""

    if output_dir is None or not str(output_dir).strip():
        return default_xlsx_image_export_dir(path)
    return Path(output_dir).expanduser().resolve()


def default_xlsx_image_mapping_path(path: str | Path, output_dir: str | Path | None = None) -> Path:
    """Build the default mapping CSV path next to extracted images."""

    file_path = Path(path).expanduser().resolve()
    export_dir = resolve_xlsx_image_export_dir(file_path, output_dir=output_dir)
    return export_dir / f"{file_path.stem}_image_mapping.csv"


def write_image_mapping_csv(path: str | Path, records: Sequence[DiamondRecord]) -> int:
    """Write a simple row-to-image mapping CSV for extracted workbook images."""

    file_path = Path(path).expanduser()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_row", "artikel_nr", "referenz", "bild"],
        )
        writer.writeheader()
        for record in records:
            image_ref = str(record.data.get("Bild", "")).strip()
            if not image_ref:
                continue
            writer.writerow(
                {
                    "source_row": str(record.source_row),
                    "artikel_nr": record.data.get("Artikel Nr", ""),
                    "referenz": record.data.get("Referenz", ""),
                    "bild": image_ref,
                }
            )
            written += 1

    return written


def _resolve_archive_target(base_path: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = PurePosixPath(base_path).parent
    return posixpath.normpath(str(base_dir / target))


def _drawing_path_for_sheet(archive: zipfile.ZipFile, sheet_path: str) -> str | None:
    sheet_rel_path = f"{PurePosixPath(sheet_path).parent.as_posix()}/_rels/{PurePosixPath(sheet_path).name}.rels"
    try:
        rels_xml = ET.fromstring(archive.read(sheet_rel_path))
    except KeyError:
        return None

    for relationship in rels_xml.findall("r:Relationship", _PKG_REL_NS):
        if relationship.attrib.get("Type") != _DRAWING_REL_TYPE:
            continue
        target = relationship.attrib.get("Target", "")
        if not target:
            continue
        return _resolve_archive_target(sheet_path, target)
    return None


def _drawing_rel_map(archive: zipfile.ZipFile, drawing_path: str) -> dict[str, str]:
    rel_path = f"{PurePosixPath(drawing_path).parent.as_posix()}/_rels/{PurePosixPath(drawing_path).name}.rels"
    try:
        rels_xml = ET.fromstring(archive.read(rel_path))
    except KeyError:
        return {}

    mapping: dict[str, str] = {}
    for relationship in rels_xml.findall("r:Relationship", _PKG_REL_NS):
        rel_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target", "")
        if not rel_id or not target:
            continue
        mapping[rel_id] = _resolve_archive_target(drawing_path, target)
    return mapping


def _product_image_column_limit(keep_indexes: Sequence[int], final_header: Sequence[str]) -> int:
    non_image_columns = [
        column_index
        for column_index, header in zip(keep_indexes, final_header, strict=False)
        if header != "Bild"
    ]
    if non_image_columns:
        return min(non_image_columns)
    if keep_indexes:
        return max(keep_indexes) + 1
    return 1


def _match_anchor_row(anchor_row: int, source_rows: set[int]) -> int | None:
    if anchor_row in source_rows:
        return anchor_row

    for delta in (1, -1, 2, -2):
        candidate = anchor_row + delta
        if candidate in source_rows:
            return candidate
    return None


def extract_xlsx_row_images(
    path: str | Path,
    *,
    sheet_path: str,
    header_row: int,
    keep_indexes: Sequence[int],
    final_header: Sequence[str],
    source_rows: Sequence[int],
    output_dir: str | Path | None = None,
) -> dict[int, list[Path]]:
    """Extract embedded images from the first worksheet and map them to product rows."""

    file_path = Path(path).expanduser().resolve()
    export_dir = resolve_xlsx_image_export_dir(file_path, output_dir=output_dir)
    source_row_set = set(source_rows)
    if not source_row_set:
        return {}

    image_column_limit = _product_image_column_limit(keep_indexes, final_header)
    row_images: dict[int, list[Path]] = {}

    with zipfile.ZipFile(file_path) as archive:
        drawing_path = _drawing_path_for_sheet(archive, sheet_path)
        if drawing_path is None:
            return {}

        try:
            drawing_xml = ET.fromstring(archive.read(drawing_path))
        except KeyError:
            return {}

        rel_map = _drawing_rel_map(archive, drawing_path)
        anchors = drawing_xml.findall("xdr:twoCellAnchor", _XDR_NS) + drawing_xml.findall("xdr:oneCellAnchor", _XDR_NS)

        export_dir.mkdir(parents=True, exist_ok=True)
        exported_files: dict[str, Path] = {}

        for anchor in anchors:
            picture = anchor.find("xdr:pic", _XDR_NS)
            if picture is None:
                continue

            from_node = anchor.find("xdr:from", _XDR_NS)
            if from_node is None:
                continue

            try:
                anchor_row = int(from_node.findtext("xdr:row", default="0", namespaces=_XDR_NS))
                anchor_col = int(from_node.findtext("xdr:col", default="0", namespaces=_XDR_NS))
            except ValueError:
                continue

            if anchor_row < header_row or anchor_col >= image_column_limit:
                continue

            matched_row = _match_anchor_row(anchor_row, source_row_set)
            if matched_row is None:
                continue

            blip = picture.find(".//a:blip", _XDR_NS)
            if blip is None:
                continue

            rel_id = blip.attrib.get(_OFFICE_REL_EMBED)
            media_archive_path = rel_map.get(rel_id or "")
            if not media_archive_path or not media_archive_path.startswith("xl/media/"):
                continue

            exported_path = exported_files.get(media_archive_path)
            if exported_path is None:
                exported_path = export_dir / Path(media_archive_path).name
                if not exported_path.exists():
                    exported_path.write_bytes(archive.read(media_archive_path))
                exported_files[media_archive_path] = exported_path

            row_images.setdefault(matched_row, []).append(exported_path)

    return row_images
