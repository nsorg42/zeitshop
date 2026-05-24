from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import socket
import ssl
import time
from typing import Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from ..core.models import ConversionBatch, ImageArchiveOptions, Severity, ValidationIssue
from ..core.normalize import normalize_text

MANIFEST_COLUMNS = [
    "article_id",
    "reference",
    "barcode",
    "picture_index",
    "source_url",
    "local_path",
    "sha256",
    "content_type",
    "byte_size",
    "downloaded_at",
]

_LOOKUP_RE = re.compile(r"[^0-9a-z]+")
_UPLOAD_CACHE_PATH = Path.home() / ".zeitshop_converter" / "wix_media_cache.json"
_UPLOAD_TIMEOUT_SECONDS = 180.0
_UPLOAD_POLL_SECONDS = 1.5
_WIX_UPLOAD_CONNECTIVITY_TIMEOUT_SECONDS = 5.0
_WIX_UPLOAD_OFFLINE_MESSAGE = "Internet nötig um Bilder automatisch hochzuladen"

ProgressCallback = Callable[[str], None]


class WixUploadConnectivityError(ConnectionError):
    """Raised when a Wix media upload is requested without internet connectivity."""


@dataclass(frozen=True)
class ArchivedImage:
    """One local image file from the DiamondSEVEN archive manifest."""

    article_id: str
    reference: str
    barcode: str
    picture_index: int
    source_url: str
    local_path: Path
    sha256: str
    content_type: str
    byte_size: int
    downloaded_at: str


@dataclass(frozen=True)
class ArchiveReport:
    """Counts produced by a DiamondSEVEN image archive run."""

    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    duplicate_urls: int = 0
    missing_pictures: int = 0
    unmatched_metadata: int = 0


@dataclass(frozen=True)
class MatchResult:
    """Image match result for one DIAMOND export row."""

    images: list[ArchivedImage]
    matched_by: str
    article_ids: list[str]


@dataclass(frozen=True)
class MatchDiagnostic:
    """Serializable image-match diagnostic for one DIAMOND export row."""

    source_row: int
    artikel_nr: str
    referenz: str
    status: str
    matched_by: str
    article_ids: str
    image_count: int


def ensure_wix_upload_connectivity() -> None:
    """Fail fast when Wix uploads are requested without internet connectivity."""

    try:
        with socket.create_connection(
            ("www.wixapis.com", 443),
            timeout=_WIX_UPLOAD_CONNECTIVITY_TIMEOUT_SECONDS,
        ):
            pass
    except OSError as exc:
        raise WixUploadConnectivityError(_WIX_UPLOAD_OFFLINE_MESSAGE) from exc


def _lookup_key(value: str | None) -> str:
    return _LOOKUP_RE.sub("", normalize_text(value).casefold())


def _api_text(value: object) -> str:
    if value is None:
        return ""
    return normalize_text(str(value))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_ssl_context(
    *,
    ca_bundle: str | Path | None = None,
    insecure_skip_tls_verify: bool = False,
) -> ssl.SSLContext | None:
    """Build an optional TLS context for DiamondSEVEN archive downloads."""

    if insecure_skip_tls_verify:
        return ssl._create_unverified_context()
    if ca_bundle is None or not str(ca_bundle).strip():
        return None
    return ssl.create_default_context(cafile=str(Path(ca_bundle).expanduser()))


def _content_type_extension(content_type: str) -> str:
    content_type = content_type.split(";", 1)[0].strip().casefold()
    if content_type == "image/jpeg":
        return ".jpg"
    return mimetypes.guess_extension(content_type) or ""


def _url_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.casefold()
    if suffix in {".avif", ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ""


def _row_to_image(row: Mapping[str, str]) -> ArchivedImage:
    return ArchivedImage(
        article_id=normalize_text(row.get("article_id")),
        reference=normalize_text(row.get("reference")),
        barcode=normalize_text(row.get("barcode")),
        picture_index=int(normalize_text(row.get("picture_index")) or "0"),
        source_url=normalize_text(row.get("source_url")),
        local_path=Path(normalize_text(row.get("local_path"))).expanduser(),
        sha256=normalize_text(row.get("sha256")),
        content_type=normalize_text(row.get("content_type")),
        byte_size=int(normalize_text(row.get("byte_size")) or "0"),
        downloaded_at=normalize_text(row.get("downloaded_at")),
    )


def load_manifest(path: str | Path) -> list[ArchivedImage]:
    """Load a DiamondSEVEN image manifest."""

    manifest_path = Path(path).expanduser()
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [_row_to_image(row) for row in reader]


def write_manifest(path: str | Path, images: Sequence[ArchivedImage]) -> int:
    """Write a DiamondSEVEN image manifest."""

    manifest_path = Path(path).expanduser()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for image in images:
            writer.writerow(
                {
                    "article_id": image.article_id,
                    "reference": image.reference,
                    "barcode": image.barcode,
                    "picture_index": str(image.picture_index),
                    "source_url": image.source_url,
                    "local_path": str(image.local_path),
                    "sha256": image.sha256,
                    "content_type": image.content_type,
                    "byte_size": str(image.byte_size),
                    "downloaded_at": image.downloaded_at,
                }
            )
    return len(images)


class ImageManifestIndex:
    """Lookup helper for matching DIAMOND CSV rows to archived images."""

    def __init__(self, images: Sequence[ArchivedImage]) -> None:
        self._images_by_article: dict[str, list[ArchivedImage]] = {}
        self._by_article_id: dict[str, set[str]] = {}
        self._by_reference: dict[str, set[str]] = {}
        self._by_barcode: dict[str, set[str]] = {}

        for image in images:
            article_id = normalize_text(image.article_id)
            if not article_id:
                continue
            self._images_by_article.setdefault(article_id, []).append(image)
            self._index(self._by_article_id, image.article_id, article_id)
            self._index(self._by_reference, image.reference, article_id)
            self._index(self._by_barcode, image.barcode, article_id)

        for values in self._images_by_article.values():
            values.sort(key=lambda image: image.picture_index)

    @classmethod
    def from_path(cls, path: str | Path) -> "ImageManifestIndex":
        return cls(load_manifest(path))

    def _index(self, target: dict[str, set[str]], value: str, article_id: str) -> None:
        key = _lookup_key(value)
        if not key:
            return
        target.setdefault(key, set()).add(article_id)

    def match_source(self, source: Mapping[str, str]) -> MatchResult:
        artikel_nr = normalize_text(source.get("Artikel Nr"))
        referenz = normalize_text(source.get("Referenz"))
        checks = (
            ("artikel_nr_article_id", self._by_article_id, artikel_nr),
            ("artikel_nr_reference", self._by_reference, artikel_nr),
            ("referenz_reference", self._by_reference, referenz),
            ("referenz_barcode", self._by_barcode, referenz),
        )

        for matched_by, index, value in checks:
            key = _lookup_key(value)
            if not key:
                continue
            article_ids = sorted(index.get(key, set()))
            if not article_ids:
                continue
            if len(article_ids) > 1:
                return MatchResult(images=[], matched_by=f"ambiguous:{matched_by}", article_ids=article_ids)
            article_id = article_ids[0]
            return MatchResult(
                images=list(self._images_by_article.get(article_id, [])),
                matched_by=matched_by,
                article_ids=[article_id],
            )

        return MatchResult(images=[], matched_by="none", article_ids=[])


def diagnose_image_matches(records: Sequence[Mapping[str, object]], manifest_path: str | Path) -> list[MatchDiagnostic]:
    """Compare parsed DIAMOND records against an image manifest."""

    index = ImageManifestIndex.from_path(manifest_path)
    diagnostics: list[MatchDiagnostic] = []
    for record in records:
        source = record.data if hasattr(record, "data") else record
        source_row = int(getattr(record, "source_row", 0))
        match = index.match_source(source)
        if match.matched_by == "none":
            status = "missing"
        elif match.matched_by.startswith("ambiguous:"):
            status = "ambiguous"
        elif match.images:
            status = "matched"
        else:
            status = "matched_without_images"
        diagnostics.append(
            MatchDiagnostic(
                source_row=source_row,
                artikel_nr=normalize_text(source.get("Artikel Nr")),
                referenz=normalize_text(source.get("Referenz")),
                status=status,
                matched_by=match.matched_by,
                article_ids=";".join(match.article_ids),
                image_count=len(match.images),
            )
        )
    return diagnostics


def write_match_diagnostics(path: str | Path, diagnostics: Sequence[MatchDiagnostic]) -> int:
    """Write image-match diagnostics as CSV."""

    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_row", "artikel_nr", "referenz", "status", "matched_by", "article_ids", "image_count"],
        )
        writer.writeheader()
        for diagnostic in diagnostics:
            writer.writerow(
                {
                    "source_row": str(diagnostic.source_row),
                    "artikel_nr": diagnostic.artikel_nr,
                    "referenz": diagnostic.referenz,
                    "status": diagnostic.status,
                    "matched_by": diagnostic.matched_by,
                    "article_ids": diagnostic.article_ids,
                    "image_count": str(diagnostic.image_count),
                }
            )
    return len(diagnostics)


class DiamondSevenClient:
    """Small DiamondSEVEN Data Exchange API client for image archiving."""

    def __init__(
        self,
        base_url: str,
        partner_key: str,
        api_version: str = "1.0",
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.partner_key = partner_key
        self.api_version = api_version
        self.ssl_context = ssl_context

    def export(self, document_type: str) -> list[dict[str, object]]:
        url = self._export_url(document_type)
        request = Request(url, headers={"PartnerKey": self.partner_key, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=120.0, context=self.ssl_context) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"DiamondSEVEN API request failed with HTTP {exc.code}: {details or exc.reason}") from exc
        except URLError as exc:
            raise ValueError(f"DiamondSEVEN API request failed: {exc.reason}") from exc

        payload = json.loads(raw) if raw else []
        if not isinstance(payload, list):
            raise ValueError(f"DiamondSEVEN export/{document_type} did not return a JSON array.")
        return [item for item in payload if isinstance(item, dict)]

    def _export_url(self, document_type: str) -> str:
        base = self.base_url
        if "dataexchange" not in base:
            base = f"{base}/api/v1/diamond/dataexchange"
        query = urlencode({"version": self.api_version})
        return f"{base.rstrip('/')}/export/{document_type.strip('/')}/?{query}"


def _article_picture_urls(article: Mapping[str, object]) -> list[str]:
    pictures = article.get("ArticlePictures")
    if not isinstance(pictures, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for picture in pictures:
        if not isinstance(picture, Mapping):
            continue
        url = _api_text(picture.get("PictureURL"))
        if not url:
            continue
        key = url.casefold()
        if key in seen:
            continue
        seen.add(key)
        urls.append(url)
    return urls


def _webstock_barcodes(rows: Iterable[Mapping[str, object]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        article_id = _api_text(row.get("ArticleId"))
        barcode = _api_text(row.get("Barcode"))
        if article_id and barcode:
            result[article_id] = barcode
    return result


def _normalize_export_articles(document_type: str, rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return article-shaped dictionaries from supported DiamondSEVEN exports."""

    if document_type in {"articles", "webstock"}:
        return [dict(row) for row in rows]

    if document_type != "stock":
        raise ValueError(f"Unsupported DiamondSEVEN image archive document type: {document_type}")

    by_article_id: dict[str, dict[str, object]] = {}
    for branch in rows:
        stock_rows = branch.get("Stock")
        if not isinstance(stock_rows, list):
            continue
        for stock_row in stock_rows:
            if not isinstance(stock_row, Mapping):
                continue
            article = stock_row.get("Article")
            if not isinstance(article, Mapping):
                continue
            article_id = _api_text(article.get("ArticleId"))
            if not article_id:
                continue
            if article_id not in by_article_id:
                by_article_id[article_id] = dict(article)

    return list(by_article_id.values())


def _try_export_articles(
    client: DiamondSevenClient,
    document_type: str,
    progress_callback: ProgressCallback | None,
) -> tuple[str, list[dict[str, object]]]:
    if document_type != "auto":
        rows = client.export(document_type)
        return document_type, _normalize_export_articles(document_type, rows)

    errors: list[str] = []
    for candidate in ("articles", "stock", "webstock"):
        try:
            rows = client.export(candidate)
            articles = _normalize_export_articles(candidate, rows)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
            if progress_callback is not None:
                progress_callback(f"DiamondSEVEN export '{candidate}' skipped: {exc}")
            continue
        if progress_callback is not None:
            progress_callback(f"DiamondSEVEN export '{candidate}' selected.")
        return candidate, articles

    raise ValueError("No usable DiamondSEVEN image export succeeded. " + " | ".join(errors))


def _existing_manifest_by_url(path: str | Path) -> dict[str, ArchivedImage]:
    manifest_path = Path(path).expanduser()
    if not manifest_path.exists():
        return {}
    return {image.source_url: image for image in load_manifest(manifest_path)}


def _download_bytes(url: str, ssl_context: ssl.SSLContext | None = None) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "zeitshop-converter/0.1"})
    with urlopen(request, timeout=120.0, context=ssl_context) as response:
        data = response.read()
        content_type = normalize_text(response.headers.get("Content-Type"))
    return data, content_type


def _archive_file_path(output_dir: Path, article_id: str, picture_index: int, url: str, content_type: str) -> Path:
    ext = _url_extension(url) or _content_type_extension(content_type) or ".jpg"
    return output_dir / "files" / article_id / f"{picture_index:02d}{ext}"


def archive_diamondseven_images(
    *,
    base_url: str,
    partner_key: str,
    output_dir: str | Path,
    manifest_path: str | Path,
    api_version: str = "1.0",
    document_type: str = "auto",
    include_webstock: bool = True,
    ca_bundle: str | Path | None = None,
    insecure_skip_tls_verify: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> ArchiveReport:
    """Download all DiamondSEVEN article pictures into a local archive."""

    ssl_context = build_ssl_context(
        ca_bundle=ca_bundle,
        insecure_skip_tls_verify=insecure_skip_tls_verify,
    )
    client = DiamondSevenClient(
        base_url=base_url,
        partner_key=partner_key,
        api_version=api_version,
        ssl_context=ssl_context,
    )
    selected_document_type, articles = _try_export_articles(
        client=client,
        document_type=document_type,
        progress_callback=progress_callback,
    )
    barcodes: dict[str, str] = {}
    if include_webstock and selected_document_type != "webstock":
        try:
            barcodes = _webstock_barcodes(client.export("webstock"))
        except Exception as exc:
            if progress_callback is not None:
                progress_callback(f"WebStock metadata skipped: {exc}")

    output_path = Path(output_dir).expanduser().resolve()
    existing_by_url = _existing_manifest_by_url(manifest_path)
    images: list[ArchivedImage] = []
    seen_urls: set[str] = set()
    report = {
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "duplicate_urls": 0,
        "missing_pictures": 0,
        "unmatched_metadata": 0,
    }

    for article_number, article in enumerate(articles, start=1):
        article_id = _api_text(article.get("ArticleId"))
        reference = _api_text(article.get("Reference"))
        if not article_id:
            report["unmatched_metadata"] += 1
            continue
        picture_urls = _article_picture_urls(article)
        if not picture_urls:
            report["missing_pictures"] += 1
            continue

        for picture_index, source_url in enumerate(picture_urls, start=1):
            if progress_callback is not None:
                progress_callback(f"DiamondSEVEN Bilder {article_number}/{len(articles)}: {article_id} ({picture_index})")
            if source_url.casefold() in seen_urls:
                report["duplicate_urls"] += 1
                continue
            seen_urls.add(source_url.casefold())

            existing = existing_by_url.get(source_url)
            if existing is not None and existing.local_path.exists():
                try:
                    if _sha256_file(existing.local_path) == existing.sha256:
                        images.append(existing)
                        report["skipped"] += 1
                        continue
                except OSError:
                    pass

            try:
                data, content_type = _download_bytes(source_url, ssl_context=ssl_context)
            except Exception as exc:
                report["failed"] += 1
                if progress_callback is not None:
                    progress_callback(f"Bild-Download fehlgeschlagen: {source_url} ({exc})")
                continue

            digest = _sha256_bytes(data)
            target = _archive_file_path(output_path, article_id, picture_index, source_url, content_type)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            image = ArchivedImage(
                article_id=article_id,
                reference=reference,
                barcode=barcodes.get(article_id, ""),
                picture_index=picture_index,
                source_url=source_url,
                local_path=target,
                sha256=digest,
                content_type=content_type,
                byte_size=len(data),
                downloaded_at=_now_iso(),
            )
            images.append(image)
            report["downloaded"] += 1

    images.sort(key=lambda image: (image.article_id, image.picture_index))
    write_manifest(manifest_path, images)
    return ArchiveReport(**report)


class WixMediaClient:
    """Upload archived local image files to Wix Media Manager and cache URLs."""

    def __init__(
        self,
        site_id: str,
        api_key: str,
        file_path: str = "/zeitshop",
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.site_id = site_id
        self.api_key = api_key
        self.progress_callback = progress_callback
        self._connectivity_checked = False
        normalized_path = normalize_text(file_path).replace("\\", "/")
        if normalized_path and not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        self.file_path = normalized_path
        self._cache = self._load_cache()

    def upload_archived_image(self, image: ArchivedImage) -> str:
        resolved_path = image.local_path.expanduser().resolve()
        cache_key = self._cache_key(image)
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            cached_url = normalize_text(cached.get("url"))
            if cached_url:
                return cached_url

        self._ensure_connectivity()

        mime_type = image.content_type or mimetypes.guess_type(resolved_path.name)[0] or "application/octet-stream"
        payload: dict[str, object] = {
            "mimeType": mime_type,
            "fileName": resolved_path.name,
            "private": False,
            "labels": ["zeitshop", "diamond-import"],
        }
        if self.file_path:
            payload["filePath"] = self.file_path

        response = self._request_json(
            method="POST",
            url="https://www.wixapis.com/site-media/v1/files/generate-upload-url",
            body=payload,
            authenticated=True,
        )
        upload_url = normalize_text(response.get("uploadUrl"))
        if not upload_url:
            raise ValueError("Wix did not return an upload URL.")

        file_id = normalize_text(response.get("fileId"))
        self._report_progress(f"Wix-Upload: {resolved_path.name}")
        upload_result = self._upload_binary(upload_url=upload_url, path=resolved_path, mime_type=mime_type)
        upload_descriptor = self._unwrap_descriptor(upload_result)
        file_id = (
            file_id
            or normalize_text(upload_descriptor.get("id"))
            or normalize_text(upload_result.get("id"))
            or normalize_text(upload_result.get("fileId"))
        )
        if not file_id:
            raise ValueError("Could not determine the Wix file ID after upload.")

        descriptor = self._wait_for_ready(file_id)
        media_url = self._extract_media_url(descriptor)
        if not media_url:
            raise ValueError(f"Wix file {file_id!r} did not return a public media URL.")

        self._cache[cache_key] = {"file_id": file_id, "url": media_url}
        self._save_cache()
        return media_url

    def _ensure_connectivity(self) -> None:
        if self._connectivity_checked:
            return
        ensure_wix_upload_connectivity()
        self._connectivity_checked = True

    def _cache_key(self, image: ArchivedImage) -> str:
        return "|".join([self.site_id, image.sha256, str(image.byte_size)])

    def _load_cache(self) -> dict[str, dict[str, str]]:
        if not _UPLOAD_CACHE_PATH.exists():
            return {}
        try:
            payload = json.loads(_UPLOAD_CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, dict)
        }

    def _save_cache(self) -> None:
        try:
            _UPLOAD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _UPLOAD_CACHE_PATH.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return

    def _wait_for_ready(self, file_id: str) -> dict[str, object]:
        deadline = time.monotonic() + _UPLOAD_TIMEOUT_SECONDS
        encoded_file_id = quote(file_id, safe="")
        url = f"https://www.wixapis.com/site-media/v1/files/get-file-by-id?fileId={encoded_file_id}"
        self._report_progress(f"Wix verarbeitet Datei: {file_id}")

        while time.monotonic() < deadline:
            response = self._request_json(method="GET", url=url, authenticated=True)
            descriptor = self._unwrap_descriptor(response)
            media_url = self._extract_media_url(descriptor)
            status = normalize_text(descriptor.get("operationStatus")).upper()
            state = normalize_text(descriptor.get("state")).upper()

            if media_url:
                return descriptor
            if status in {"FAILED", "ERROR"} or state in {"FAILED", "ERROR"}:
                raise ValueError(f"Wix marked uploaded file {file_id!r} as {status or state}.")
            if not descriptor or (not status and not state):
                raise ValueError(f"Wix returned no usable processing status for file {file_id!r}.")

            time.sleep(_UPLOAD_POLL_SECONDS)

        raise TimeoutError(f"Wix did not finish processing {file_id!r} within the timeout.")

    def _report_progress(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)

    def _unwrap_descriptor(self, payload: dict[str, object]) -> dict[str, object]:
        descriptor = payload.get("fileDescriptor")
        if isinstance(descriptor, dict):
            return descriptor
        file_descriptor = payload.get("file")
        if isinstance(file_descriptor, dict):
            return file_descriptor
        return payload

    def _extract_media_url(self, descriptor: dict[str, object]) -> str:
        direct_url = normalize_text(descriptor.get("url"))
        if direct_url:
            return direct_url
        media = descriptor.get("media")
        if isinstance(media, dict):
            image_block = media.get("image")
            if isinstance(image_block, dict):
                nested_image = image_block.get("image")
                if isinstance(nested_image, dict):
                    nested_url = normalize_text(nested_image.get("url"))
                    if nested_url:
                        return nested_url
        return normalize_text(descriptor.get("thumbnailUrl"))

    def _upload_binary(self, upload_url: str, path: Path, mime_type: str) -> dict[str, object]:
        data = path.read_bytes()
        parsed = urlparse(upload_url)
        separator = "&" if parsed.query else "?"
        target_url = f"{upload_url}{separator}filename={quote(path.name)}"
        request = Request(
            target_url,
            data=data,
            method="PUT",
            headers={"Content-Type": mime_type},
        )
        try:
            with urlopen(request, timeout=_UPLOAD_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Wix upload failed with HTTP {exc.code}: {details or exc.reason}") from exc
        except URLError as exc:
            raise ValueError(f"Wix upload failed: {exc.reason}") from exc

        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]
        return {}

    def _request_json(
        self,
        method: str,
        url: str,
        body: dict[str, object] | None = None,
        authenticated: bool = False,
    ) -> dict[str, object]:
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else None
        auth_attempts = (False, True) if authenticated else (False,)
        last_error: Exception | None = None

        for use_bearer in auth_attempts:
            headers = {"Accept": "application/json"}
            if body_bytes is not None:
                headers["Content-Type"] = "application/json"
            if authenticated:
                headers["Authorization"] = f"Bearer {self.api_key}" if use_bearer else self.api_key
                headers["wix-site-id"] = self.site_id

            request = Request(url, data=body_bytes, method=method, headers=headers)
            try:
                with urlopen(request, timeout=_UPLOAD_TIMEOUT_SECONDS) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                    return json.loads(raw) if raw else {}
            except HTTPError as exc:
                last_error = exc
                if authenticated and exc.code in {401, 403} and not use_bearer:
                    continue
                details = exc.read().decode("utf-8", errors="replace")
                raise ValueError(f"Wix API request failed with HTTP {exc.code}: {details or exc.reason}") from exc
            except URLError as exc:
                last_error = exc
                raise ValueError(f"Wix API request failed: {exc.reason}") from exc

        if last_error is not None:
            raise ValueError(str(last_error))
        return {}


def _display_name(result_handle: str, result_name: str, index: int, total: int) -> str:
    base = result_name or result_handle or "Produkt"
    if total <= 1:
        return base
    return f"{base} ({index}/{total})"


def _build_media_row(header: list[str], handle: str, media_url: str, alt_text: str) -> dict[str, str]:
    row = {column: "" for column in header}
    row["handle"] = handle
    row["fieldType"] = "MEDIA"
    row["media"] = media_url
    if "mediaAltText" in row:
        row["mediaAltText"] = alt_text
    return row


def attach_archive_media_rows(
    batch: ConversionBatch,
    options: ImageArchiveOptions,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """Match archived DIAMOND images, upload them to Wix, and append MEDIA rows."""

    if not options.enabled:
        return
    if "media" not in batch.header:
        raise ValueError("Template CSV is missing the 'media' column required for image archive media rows.")

    manifest_path = normalize_text(options.manifest_path)
    if not manifest_path:
        raise ValueError("Image archive is enabled but no manifest path was configured.")

    index = ImageManifestIndex.from_path(manifest_path)
    wix_site_id = normalize_text(options.wix_site_id)
    wix_api_key = normalize_text(options.wix_api_key)
    uploader = None
    if wix_site_id and wix_api_key:
        uploader = WixMediaClient(
            site_id=wix_site_id,
            api_key=wix_api_key,
            file_path=options.wix_file_path,
            progress_callback=progress_callback,
        )

    total = len(batch.results)
    max_images = max(options.max_images_per_product, 0)
    for row_index, result in enumerate(batch.results, start=1):
        name = normalize_text(result.wix_row.get("name"))
        handle = normalize_text(result.wix_row.get("handle"))
        if progress_callback is not None:
            progress_callback(f"Bilder {row_index}/{total}: {_display_name(handle, name, 1, 1)}")

        match = index.match_source(result.source)
        if match.matched_by == "none":
            result.issues.append(
                ValidationIssue(
                    source_row=result.source_row,
                    field="media",
                    severity=Severity.WARNING,
                    message="No archived image matched this product.",
                )
            )
            continue
        if match.matched_by.startswith("ambiguous:"):
            result.issues.append(
                ValidationIssue(
                    source_row=result.source_row,
                    field="media",
                    severity=Severity.WARNING,
                    message=f"Archived image match is ambiguous across ArticleIds: {', '.join(match.article_ids)}.",
                )
            )
            continue
        if not match.images:
            result.issues.append(
                ValidationIssue(
                    source_row=result.source_row,
                    field="media",
                    severity=Severity.WARNING,
                    message=f"Archived image match '{match.article_ids[0]}' has no image files.",
                )
            )
            continue
        if uploader is None:
            result.issues.append(
                ValidationIssue(
                    source_row=result.source_row,
                    field="media",
                    severity=Severity.WARNING,
                    message="Archived image found but Wix upload is not configured.",
                )
            )
            continue

        media_urls: list[str] = []
        for image in match.images[:max_images]:
            try:
                media_urls.append(uploader.upload_archived_image(image))
            except WixUploadConnectivityError:
                raise
            except Exception as exc:
                result.issues.append(
                    ValidationIssue(
                        source_row=result.source_row,
                        field="media",
                        severity=Severity.WARNING,
                        message=f"Failed to upload archived image '{image.local_path.name}' to Wix: {exc}",
                    )
                )

        result.media_rows.extend(
            _build_media_row(
                header=batch.header,
                handle=handle,
                media_url=media_url,
                alt_text=_display_name(handle, name, index_number, len(media_urls)),
            )
            for index_number, media_url in enumerate(media_urls, start=1)
        )
