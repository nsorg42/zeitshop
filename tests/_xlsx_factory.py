from __future__ import annotations

import base64
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from openpyxl import Workbook


_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_DRAWING_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <xdr:oneCellAnchor>
    <xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>10</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
    <xdr:ext cx="76200" cy="76200"/>
    <xdr:pic>
      <xdr:nvPicPr><xdr:cNvPr id="1" name="Picture 1"/><xdr:cNvPicPr/></xdr:nvPicPr>
      <xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
      <xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>
    </xdr:pic>
    <xdr:clientData/>
  </xdr:oneCellAnchor>
  <xdr:oneCellAnchor>
    <xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>19</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
    <xdr:ext cx="76200" cy="76200"/>
    <xdr:pic>
      <xdr:nvPicPr><xdr:cNvPr id="2" name="Picture 2"/><xdr:cNvPicPr/></xdr:nvPicPr>
      <xdr:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
      <xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>
    </xdr:pic>
    <xdr:clientData/>
  </xdr:oneCellAnchor>
  <xdr:oneCellAnchor>
    <xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>22</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
    <xdr:ext cx="76200" cy="76200"/>
    <xdr:pic>
      <xdr:nvPicPr><xdr:cNvPr id="3" name="Picture 3"/><xdr:cNvPicPr/></xdr:nvPicPr>
      <xdr:blipFill><a:blip r:embed="rId3"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
      <xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>
    </xdr:pic>
    <xdr:clientData/>
  </xdr:oneCellAnchor>
</xdr:wsDr>
"""
_DRAWING_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image2.png"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image2.png"/>
</Relationships>
"""
_SHEET_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
</Relationships>
"""
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9VE3to4AAAAASUVORK5CYII="
)


def build_sample_diamond_xlsx(path: Path) -> Path:
    """Create a compact DIAMOND-style workbook with embedded worksheet images."""

    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    worksheet = workbook.active

    worksheet["A2"] = "Lager"
    worksheet["A7"] = "Kriterien:"
    worksheet["A9"] = "Bild"
    worksheet["B9"] = "Artikel Nr"
    worksheet["C9"] = "Kurzbeschreibung"
    worksheet["D9"] = "Referenz"
    worksheet["E9"] = "Menge"
    worksheet["F9"] = "Einstand"
    worksheet["G9"] = "Verkauf"

    rows = {
        11: ("SKU-1201", "Demo Orbit", "REF-SKU-1201", 1, "1'775.00", "3'550.00"),
        20: ("SKU-2202", "Demo Orbit", "REF-SKU-2202-A", 2, "1'800.00", "3'600.00"),
        23: ("SKU-2202", "Demo Orbit", "REF-SKU-2202-B", 3, "1'800.00", "3'600.00"),
    }
    for row_number, values in rows.items():
        worksheet[f"B{row_number}"] = values[0]
        worksheet[f"C{row_number}"] = values[1]
        worksheet[f"D{row_number}"] = values[2]
        worksheet[f"E{row_number}"] = values[3]
        worksheet[f"F{row_number}"] = values[4]
        worksheet[f"G{row_number}"] = values[5]

    workbook.save(path)
    _embed_images(path)
    return path


def _embed_images(workbook_path: Path) -> None:
    temp_path = workbook_path.with_suffix(f"{workbook_path.suffix}.tmp")

    with zipfile.ZipFile(workbook_path) as source, zipfile.ZipFile(temp_path, "w") as target:
        for info in source.infolist():
            if info.filename == "[Content_Types].xml":
                target.writestr(info, _update_content_types(source.read(info.filename)))
            elif info.filename == "xl/worksheets/sheet1.xml":
                target.writestr(info, _update_sheet_xml(source.read(info.filename)))
            else:
                target.writestr(info, source.read(info.filename))

        target.writestr("xl/worksheets/_rels/sheet1.xml.rels", _SHEET_RELS_XML)
        target.writestr("xl/drawings/drawing1.xml", _DRAWING_XML)
        target.writestr("xl/drawings/_rels/drawing1.xml.rels", _DRAWING_RELS_XML)
        target.writestr("xl/media/image1.png", _PNG_BYTES)
        target.writestr("xl/media/image2.png", _PNG_BYTES)

    temp_path.replace(workbook_path)


def _update_content_types(payload: bytes) -> bytes:
    root = ET.fromstring(payload)
    default_tag = f"{{{_CONTENT_TYPES_NS}}}Default"
    override_tag = f"{{{_CONTENT_TYPES_NS}}}Override"

    if not any(node.attrib.get("Extension") == "png" for node in root.findall(default_tag)):
        root.append(ET.Element(default_tag, Extension="png", ContentType="image/png"))

    if not any(node.attrib.get("PartName") == "/xl/drawings/drawing1.xml" for node in root.findall(override_tag)):
        root.append(
            ET.Element(
                override_tag,
                PartName="/xl/drawings/drawing1.xml",
                ContentType="application/vnd.openxmlformats-officedocument.drawing+xml",
            )
        )

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _update_sheet_xml(payload: bytes) -> bytes:
    ET.register_namespace("r", _OFFICE_REL_NS)
    root = ET.fromstring(payload)
    drawing_tag = f"{{{_MAIN_NS}}}drawing"
    drawing_attr = f"{{{_OFFICE_REL_NS}}}id"

    if root.find(drawing_tag) is None:
        root.append(ET.Element(drawing_tag, {drawing_attr: "rId1"}))

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
