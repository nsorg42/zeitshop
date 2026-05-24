import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from zeitshop_converter.core import ConversionBatch, ImageArchiveOptions, WixRowResult
from zeitshop_converter.io import image_archive


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/json") -> None:
        self.payload = payload
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.payload


def _manifest_image(tmp_path: Path, *, article_id: str = "100", reference: str = "REF-100", barcode: str = "BAR-100"):
    image_path = tmp_path / f"{article_id}.jpg"
    image_path.write_bytes(b"image")
    digest = image_archive._sha256_file(image_path)
    return image_archive.ArchivedImage(
        article_id=article_id,
        reference=reference,
        barcode=barcode,
        picture_index=1,
        source_url=f"https://example.com/{article_id}.jpg",
        local_path=image_path,
        sha256=digest,
        content_type="image/jpeg",
        byte_size=image_path.stat().st_size,
        downloaded_at="2026-01-01T00:00:00Z",
    )


def test_manifest_matcher_uses_planned_precedence(tmp_path: Path) -> None:
    images = [
        _manifest_image(tmp_path, article_id="100", reference="REF-100", barcode="BAR-100"),
        _manifest_image(tmp_path, article_id="200", reference="ART-200", barcode="BAR-200"),
        _manifest_image(tmp_path, article_id="300", reference="REF-300", barcode="BAR-300"),
    ]
    index = image_archive.ImageManifestIndex(images)

    assert index.match_source({"Artikel Nr": "100", "Referenz": ""}).matched_by == "artikel_nr_article_id"
    assert index.match_source({"Artikel Nr": "ART-200", "Referenz": ""}).matched_by == "artikel_nr_reference"
    assert index.match_source({"Artikel Nr": "missing", "Referenz": "REF-300"}).matched_by == "referenz_reference"
    assert index.match_source({"Artikel Nr": "missing", "Referenz": "BAR-300"}).matched_by == "referenz_barcode"
    assert index.match_source({"Artikel Nr": "missing", "Referenz": "none"}).matched_by == "none"


def test_manifest_matcher_reports_ambiguous_reference(tmp_path: Path) -> None:
    images = [
        _manifest_image(tmp_path, article_id="100", reference="DUP", barcode=""),
        _manifest_image(tmp_path, article_id="200", reference="DUP", barcode=""),
    ]
    index = image_archive.ImageManifestIndex(images)

    match = index.match_source({"Artikel Nr": "DUP", "Referenz": ""})

    assert match.matched_by == "ambiguous:artikel_nr_reference"
    assert match.article_ids == ["100", "200"]


def test_archive_downloads_articles_and_enriches_barcodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    articles = [
        {"ArticleId": 100, "Reference": "REF-100", "ArticlePictures": [{"PictureURL": "https://cdn/100.jpg"}]},
        {"ArticleId": 200, "Reference": "REF-200", "ArticlePictures": []},
        {"Reference": "missing id", "ArticlePictures": [{"PictureURL": "https://cdn/missing.jpg"}]},
    ]
    webstock = [{"ArticleId": 100, "Barcode": "BAR-100"}]

    def fake_urlopen(request, timeout=0, context=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "export/articles" in url:
            return FakeResponse(json.dumps(articles).encode("utf-8"))
        if "export/webstock" in url:
            return FakeResponse(json.dumps(webstock).encode("utf-8"))
        if url == "https://cdn/100.jpg":
            return FakeResponse(b"full image bytes", content_type="image/jpeg")
        raise AssertionError(url)

    monkeypatch.setattr(image_archive, "urlopen", fake_urlopen)
    manifest_path = tmp_path / "manifest.csv"

    report = image_archive.archive_diamondseven_images(
        base_url="https://server.diamondseven.swiss:10555",
        partner_key="key",
        output_dir=tmp_path / "archive",
        manifest_path=manifest_path,
    )
    rows = image_archive.load_manifest(manifest_path)

    assert report.downloaded == 1
    assert report.missing_pictures == 1
    assert report.unmatched_metadata == 1
    assert rows[0].article_id == "100"
    assert rows[0].reference == "REF-100"
    assert rows[0].barcode == "BAR-100"
    assert rows[0].local_path.exists()


def test_archive_auto_falls_back_to_stock_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stock = [
        {
            "Stock": [
                {
                    "Article": {
                        "ArticleId": 300,
                        "Reference": "REF-300",
                        "ArticlePictures": [{"PictureURL": "https://cdn/300.jpg"}],
                    }
                }
            ]
        }
    ]

    def fake_urlopen(request, timeout=0, context=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "export/articles" in url:
            raise image_archive.HTTPError(url, 400, "Bad Request", {}, None)
        if "export/stock" in url:
            return FakeResponse(json.dumps(stock).encode("utf-8"))
        if "export/webstock" in url:
            return FakeResponse(json.dumps([]).encode("utf-8"))
        if url == "https://cdn/300.jpg":
            return FakeResponse(b"stock image bytes", content_type="image/jpeg")
        raise AssertionError(url)

    monkeypatch.setattr(image_archive, "urlopen", fake_urlopen)
    manifest_path = tmp_path / "manifest.csv"

    report = image_archive.archive_diamondseven_images(
        base_url="https://server.diamondseven.swiss:10555",
        partner_key="key",
        output_dir=tmp_path / "archive",
        manifest_path=manifest_path,
    )
    rows = image_archive.load_manifest(manifest_path)

    assert report.downloaded == 1
    assert rows[0].article_id == "300"
    assert rows[0].reference == "REF-300"


def test_attach_archive_media_rows_uploads_and_adds_media_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = _manifest_image(tmp_path, article_id="100", reference="REF-100")
    manifest_path = tmp_path / "manifest.csv"
    image_archive.write_manifest(manifest_path, [image])
    batch = ConversionBatch(
        header=["handle", "fieldType", "media", "mediaAltText"],
        results=[
            WixRowResult(
                source_row=2,
                source={"Artikel Nr": "100", "Referenz": "REF-100"},
                wix_row={"handle": "ds-100", "fieldType": "PRODUCT", "name": "Product"},
            )
        ],
    )

    monkeypatch.setattr(
        image_archive.WixMediaClient,
        "upload_archived_image",
        lambda self, archived_image: f"https://static.wixstatic.com/media/{archived_image.local_path.name}",
    )

    image_archive.attach_archive_media_rows(
        batch=batch,
        options=image_archive.ImageArchiveOptions(
            enabled=True,
            manifest_path=str(manifest_path),
            wix_site_id="site",
            wix_api_key="key",
        ),
    )

    assert batch.results[0].media_rows == [
        {
            "handle": "ds-100",
            "fieldType": "MEDIA",
            "media": "https://static.wixstatic.com/media/100.jpg",
            "mediaAltText": "Product",
        }
    ]


def test_diagnose_image_matches_writes_csv(tmp_path: Path) -> None:
    image = _manifest_image(tmp_path, article_id="100")
    manifest_path = tmp_path / "manifest.csv"
    output_path = tmp_path / "diagnostics.csv"
    image_archive.write_manifest(manifest_path, [image])

    diagnostics = image_archive.diagnose_image_matches(
        [SimpleNamespace(source_row=2, data={"Artikel Nr": "100", "Referenz": ""})],
        manifest_path,
    )
    written = image_archive.write_match_diagnostics(output_path, diagnostics)

    assert written == 1
    assert diagnostics[0].status == "matched"
    assert "artikel_nr_article_id" in output_path.read_text(encoding="utf-8")
