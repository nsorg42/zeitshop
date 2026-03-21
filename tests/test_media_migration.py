import base64
import io
import json
from pathlib import Path

import pytest
from urllib.error import HTTPError, URLError

from zeitshop_converter.conversion import convert_diamond_file
from zeitshop_converter.core import ConversionBatch, ConversionOptions, DiamondRecord, ImageMigrationOptions, convert_records
from zeitshop_converter.io import media_migration


def _template_header() -> list[str]:
    return [
        "handle",
        "fieldType",
        "name",
        "visible",
        "plainDescription",
        "media",
        "mediaAltText",
        "brand",
        "price",
        "cost",
        "inventory",
        "sku",
        "barcode",
    ]


def test_convert_file_adds_media_rows_for_explicit_image_urls(tmp_path: Path) -> None:
    file_path = tmp_path / "diamond.csv"
    file_path.write_text(
        "Bild;Artikel Nr;Kurzbeschreibung;Menge;Einstand;Verkauf\n"
        "https://example.com/images/10.jpg;10;Sample;1;5;9\n",
        encoding="utf-8",
    )

    batch = convert_diamond_file(
        diamond_csv=file_path,
        options=ConversionOptions(
            image_migration=ImageMigrationOptions(enabled=True),
        ),
    )

    assert len(batch.valid_rows) == 2
    assert batch.valid_rows[0]["fieldType"] == "PRODUCT"
    assert batch.valid_rows[1]["fieldType"] == "MEDIA"
    assert batch.valid_rows[1]["media"] == "https://example.com/images/10.jpg"
    assert batch.valid_rows[1]["mediaAltText"] == "Sample"


def test_attach_media_rows_matches_local_files_by_article_number(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "123.jpg"
    image_path.write_bytes(b"fake image bytes")

    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Bild": "",
                "Artikel Nr": "123",
                "Kurzbeschreibung": "Sample",
                "Menge": "1",
                "Einstand": "5",
                "Verkauf": "9",
            },
        )
    ]
    batch = convert_records(records, _template_header(), ConversionOptions())

    monkeypatch.setattr(
        media_migration.WixMediaClient,
        "upload_image",
        lambda self, path: f"https://static.wixstatic.com/media/{path.name}",
    )

    media_migration.attach_media_rows(
        batch=batch,
        options=ImageMigrationOptions(
            enabled=True,
            image_directory=str(tmp_path),
            wix_site_id="site-id",
            wix_api_key="api-key",
        ),
        source_file=tmp_path / "diamond.csv",
    )

    assert len(batch.valid_rows) == 2
    assert batch.valid_rows[1]["fieldType"] == "MEDIA"
    assert batch.valid_rows[1]["media"] == "https://static.wixstatic.com/media/123.jpg"


def test_attach_media_rows_warns_when_explicit_image_reference_is_missing(tmp_path: Path) -> None:
    records = [
        DiamondRecord(
            source_row=2,
            data={
                "Bild": "missing.jpg",
                "Artikel Nr": "123",
                "Kurzbeschreibung": "Sample",
                "Menge": "1",
                "Einstand": "5",
                "Verkauf": "9",
            },
        )
    ]
    batch = convert_records(records, _template_header(), ConversionOptions())

    media_migration.attach_media_rows(
        batch=batch,
        options=ImageMigrationOptions(enabled=True, image_directory=str(tmp_path)),
        source_file=tmp_path / "diamond.csv",
    )

    assert batch.results[0].media_rows == []
    assert any(
        issue.message == "Image reference could not be resolved: 'missing.jpg'."
        for issue in batch.results[0].issues
    )


def test_media_helpers_normalize_and_dedupe_values(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"img")

    assert media_migration._is_remote_url("https://example.com/a.jpg") is True
    assert media_migration._is_remote_url("ftp://example.com/a.jpg") is False
    assert media_migration._is_supported_image(image_path) is True
    assert media_migration._sanitize_lookup_key(" Ref 12-3 /A ") == "ref123a"
    assert media_migration._split_explicit_refs("a.jpg;b.jpg|c.jpg\nd.jpg") == [
        "a.jpg",
        "b.jpg",
        "c.jpg",
        "d.jpg",
    ]
    assert media_migration._dedupe_strings(["A", "a", "B"]) == ["A", "B"]
    assert media_migration._dedupe_paths([image_path, image_path]) == [image_path]
    assert media_migration._display_name("handle", "", 2, 3) == "handle (2/3)"


def test_image_library_matches_by_name_stem_sanitized_and_prefix(tmp_path: Path) -> None:
    exact = tmp_path / "123.jpg"
    exact.write_bytes(b"img")
    sanitized = tmp_path / "AB 12-3.png"
    sanitized.write_bytes(b"img")
    prefixed = tmp_path / "ref-1_extra.webp"
    prefixed.write_bytes(b"img")

    library = media_migration.ImageLibrary([tmp_path, tmp_path])

    assert library.find_matches("123") == [exact]
    assert sanitized in library.find_matches("ab123")
    assert prefixed in library.find_matches("ref-1")


def test_build_image_roots_and_resolve_explicit_paths(tmp_path: Path) -> None:
    source_file = tmp_path / "diamond.csv"
    source_file.write_text("", encoding="utf-8")
    explicit = tmp_path / "images" / "local.jpg"
    explicit.parent.mkdir()
    explicit.write_bytes(b"img")
    sanitized = tmp_path / "images" / "Ref 12-3.jpg"
    sanitized.write_bytes(b"img")

    options = ImageMigrationOptions(enabled=True, image_directory=str(explicit.parent))
    roots = media_migration._build_image_roots(options, source_file)
    assert roots == [explicit.parent, source_file.parent]

    library = media_migration.ImageLibrary(roots)
    assert media_migration._resolve_explicit_local_path(str(explicit), roots, library) == explicit
    assert media_migration._resolve_explicit_local_path("local.jpg", roots, library) == explicit
    assert media_migration._resolve_explicit_local_path("ref-123", roots, library) == sanitized


def test_collect_media_urls_handles_missing_unsupported_and_unconfigured_local_files(tmp_path: Path) -> None:
    text_file = tmp_path / "file.txt"
    text_file.write_text("not an image", encoding="utf-8")
    image_path = tmp_path / "123.jpg"
    image_path.write_bytes(b"img")
    roots = [tmp_path]
    library = media_migration.ImageLibrary(roots)

    urls, issues = media_migration._collect_media_urls(
        result_source={"Bild": "missing.jpg; file.txt", "Artikel Nr": "123"},
        search_roots=roots,
        library=library,
        uploader=None,
        source_row=2,
    )

    assert urls == []
    assert [issue.message for issue in issues] == [
        "Image reference could not be resolved: 'missing.jpg'.",
        "Unsupported image file type: 'file.txt'.",
    ]

    urls, issues = media_migration._collect_media_urls(
        result_source={"Bild": "", "Artikel Nr": "123"},
        search_roots=roots,
        library=library,
        uploader=None,
        source_row=3,
    )
    assert urls == []
    assert [issue.message for issue in issues] == [
        "Local image found but Wix upload is not configured: '123.jpg'. Set a Wix site ID and API key to migrate local files automatically."
    ]


def test_collect_media_urls_uses_article_reference_and_upload_failures(tmp_path: Path) -> None:
    article_image = tmp_path / "123.jpg"
    article_image.write_bytes(b"img")
    reference_image = tmp_path / "REF-1.png"
    reference_image.write_bytes(b"img")
    roots = [tmp_path]
    library = media_migration.ImageLibrary(roots)

    class FakeUploader:
        def upload_image(self, path: Path) -> str:
            if path.name == "REF-1.png":
                raise RuntimeError("boom")
            return f"https://static.example/{path.name}"

    urls, issues = media_migration._collect_media_urls(
        result_source={"Bild": "", "Artikel Nr": "123", "Referenz": "REF-1"},
        search_roots=roots,
        library=library,
        uploader=FakeUploader(),
        source_row=4,
    )

    assert urls == ["https://static.example/123.jpg"]
    assert [issue.message for issue in issues] == [
        "Failed to upload image 'REF-1.png' to Wix: boom"
    ]


def test_collect_media_urls_raises_connectivity_error_for_offline_uploads(tmp_path: Path) -> None:
    image_path = tmp_path / "123.jpg"
    image_path.write_bytes(b"img")
    roots = [tmp_path]
    library = media_migration.ImageLibrary(roots)

    class FakeUploader:
        def upload_image(self, path: Path) -> str:
            raise media_migration.WixUploadConnectivityError(
                "Internet nötig um Bilder automatisch hochzuladen"
            )

    with pytest.raises(
        media_migration.WixUploadConnectivityError,
        match="Internet nötig um Bilder automatisch hochzuladen",
    ):
        media_migration._collect_media_urls(
            result_source={"Bild": "", "Artikel Nr": "123"},
            search_roots=roots,
            library=library,
            uploader=FakeUploader(),
            source_row=5,
        )


def test_ensure_wix_upload_connectivity_raises_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_migration.socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
    )

    with pytest.raises(
        media_migration.WixUploadConnectivityError,
        match="Internet nötig um Bilder automatisch hochzuladen",
    ):
        media_migration.ensure_wix_upload_connectivity()


def test_build_media_row_and_attach_media_rows_progress(tmp_path: Path) -> None:
    header = _template_header()
    row = media_migration._build_media_row(header, "ds-1", "https://example.com/1.jpg", "Alt")
    assert row["handle"] == "ds-1"
    assert row["fieldType"] == "MEDIA"
    assert row["mediaAltText"] == "Alt"

    batch = ConversionBatch(header=header, results=[])
    batch.results = [
        convert_records(
            [
                DiamondRecord(
                    source_row=2,
                    data={
                        "Bild": "https://example.com/1.jpg;https://example.com/2.jpg",
                        "Artikel Nr": "123",
                        "Kurzbeschreibung": "Sample",
                        "Menge": "1",
                        "Einstand": "5",
                        "Verkauf": "9",
                    },
                )
            ],
            header,
            ConversionOptions(),
        ).results[0]
    ]

    progress: list[str] = []
    media_migration.attach_media_rows(
        batch=batch,
        options=ImageMigrationOptions(enabled=True, image_directory=str(tmp_path)),
        source_file=tmp_path / "diamond.csv",
        progress_callback=progress.append,
    )

    assert progress == ["Bilder 1/1: Sample"]
    assert [row["fieldType"] for row in batch.results[0].media_rows] == ["MEDIA", "MEDIA"]
    assert batch.results[0].media_rows[0]["mediaAltText"] == "Sample (1/2)"
    assert batch.results[0].media_rows[1]["mediaAltText"] == "Sample (2/2)"


def test_attach_media_rows_requires_media_column(tmp_path: Path) -> None:
    batch = convert_records(
        [
            DiamondRecord(
                source_row=2,
                data={"Artikel Nr": "123", "Kurzbeschreibung": "Sample", "Menge": "1", "Einstand": "5", "Verkauf": "9"},
            )
        ],
        ["handle", "fieldType", "name", "visible", "price", "cost", "inventory", "sku"],
        ConversionOptions(),
    )

    with pytest.raises(ValueError, match="missing the 'media' column"):
        media_migration.attach_media_rows(
            batch=batch,
            options=ImageMigrationOptions(enabled=True),
            source_file=tmp_path / "diamond.csv",
        )


def test_wix_media_client_uses_cache_and_normalizes_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "cache.json"
    monkeypatch.setattr(media_migration, "_UPLOAD_CACHE_PATH", cache_path)
    image_path = tmp_path / "cached.jpg"
    image_path.write_bytes(b"img")

    client = media_migration.WixMediaClient("site", "api", file_path="folder\\sub")
    cache_key = client._cache_key(image_path.resolve())
    client._cache[cache_key] = {"url": "https://cached.example/image.jpg"}
    monkeypatch.setattr(client, "_request_json", lambda **kwargs: (_ for _ in ()).throw(AssertionError("network not expected")))

    assert client.file_path == "/folder/sub"
    assert client.upload_image(image_path) == "https://cached.example/image.jpg"


def test_wix_media_client_upload_image_stores_cache_and_extracts_file_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "cache.json"
    monkeypatch.setattr(media_migration, "_UPLOAD_CACHE_PATH", cache_path)
    image_path = tmp_path / "upload.jpg"
    image_path.write_bytes(b"img")

    payload = base64.urlsafe_b64encode(json.dumps({"path": "/folder/file-123"}).encode("utf-8")).decode("ascii").rstrip("=")
    upload_url = f"https://upload.example/header.{payload}.sig"

    client = media_migration.WixMediaClient("site", "api")
    monkeypatch.setattr(client, "_request_json", lambda **kwargs: {"uploadUrl": upload_url})
    monkeypatch.setattr(client, "_upload_binary", lambda **kwargs: {})
    monkeypatch.setattr(client, "_wait_for_ready", lambda file_id: {"url": f"https://cdn.example/{file_id}.jpg"})

    assert client._extract_file_id_from_upload_url(upload_url) == "file-123"
    assert client.upload_image(image_path) == "https://cdn.example/file-123.jpg"
    assert client._cache


def test_wix_media_client_handles_nested_file_descriptor_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "cache.json"
    monkeypatch.setattr(media_migration, "_UPLOAD_CACHE_PATH", cache_path)
    image_path = tmp_path / "upload.jpg"
    image_path.write_bytes(b"img")

    client = media_migration.WixMediaClient("site", "api")
    monkeypatch.setattr(client, "_request_json", lambda **kwargs: {"uploadUrl": "https://upload.example/token"})
    monkeypatch.setattr(
        client,
        "_upload_binary",
        lambda **kwargs: {
            "file": {
                "id": "file-456",
                "url": "https://cdn.example/file-456.jpg",
                "operationStatus": "READY",
                "state": "OK",
            }
        },
    )
    monkeypatch.setattr(
        client,
        "_wait_for_ready",
        lambda file_id: {
            "id": file_id,
            "url": f"https://cdn.example/{file_id}.jpg",
            "operationStatus": "READY",
            "state": "OK",
        },
    )

    assert client.upload_image(image_path) == "https://cdn.example/file-456.jpg"


def test_wix_media_client_extracts_media_url_from_nested_image_payload() -> None:
    client = media_migration.WixMediaClient("site", "api")

    descriptor = {
        "media": {
            "image": {
                "image": {
                    "url": "https://cdn.example/nested.jpg",
                }
            }
        },
        "thumbnailUrl": "https://cdn.example/thumb.jpg",
    }
    assert client._extract_media_url(descriptor) == "https://cdn.example/nested.jpg"


def test_wix_media_client_load_cache_wait_and_request_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(media_migration, "_UPLOAD_CACHE_PATH", cache_path)

    client = media_migration.WixMediaClient("site", "api")
    assert client._cache == {}

    responses = iter(
        [
            {"fileDescriptor": {"operationStatus": "PROCESSING", "state": "PROCESSING"}},
            {"fileDescriptor": {"operationStatus": "READY", "url": "https://cdn.example/ready.jpg"}},
        ]
    )
    original_request_json = client._request_json
    monkeypatch.setattr(client, "_request_json", lambda **kwargs: next(responses))
    monkeypatch.setattr(media_migration.time, "sleep", lambda seconds: None)
    assert client._wait_for_ready("file-id") == {"operationStatus": "READY", "url": "https://cdn.example/ready.jpg"}
    monkeypatch.setattr(client, "_request_json", original_request_json)

    assert client._unwrap_descriptor({"file": {"id": "nested", "url": "https://cdn.example/file.jpg"}}) == {
        "id": "nested",
        "url": "https://cdn.example/file.jpg",
    }

    auth_headers: list[str | None] = []

    class FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return self.payload

    def fake_urlopen(request, timeout=0):
        auth = request.get_header("Authorization")
        auth_headers.append(auth)
        if auth == "api":
            raise HTTPError(request.full_url, 401, "unauthorized", hdrs=None, fp=io.BytesIO(b"nope"))
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(media_migration, "urlopen", fake_urlopen)
    assert client._request_json("GET", "https://example.com/api", authenticated=True) == {"ok": True}
    assert auth_headers == ["api", "Bearer api"]


def test_wix_media_client_upload_binary_handles_payload_shapes_and_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "cache.json"
    monkeypatch.setattr(media_migration, "_UPLOAD_CACHE_PATH", cache_path)
    image_path = tmp_path / "upload.jpg"
    image_path.write_bytes(b"img")
    client = media_migration.WixMediaClient("site", "api")

    class FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return self.payload

    monkeypatch.setattr(media_migration, "urlopen", lambda request, timeout=0: FakeResponse(b'[{"id":"123"}]'))
    assert client._upload_binary("https://upload.example", image_path, "image/jpeg") == {"id": "123"}

    def raise_url_error(request, timeout=0):
        raise URLError("offline")

    monkeypatch.setattr(media_migration, "urlopen", raise_url_error)
    with pytest.raises(ValueError, match="Wix upload failed: offline"):
        client._upload_binary("https://upload.example", image_path, "image/jpeg")
