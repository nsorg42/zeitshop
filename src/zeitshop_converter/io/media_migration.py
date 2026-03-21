from __future__ import annotations

import base64
from collections.abc import Mapping
import json
import mimetypes
from pathlib import Path
import re
import socket
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from ..core.models import ConversionBatch, ImageMigrationOptions, Severity, ValidationIssue
from ..core.normalize import normalize_text

_SUPPORTED_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
_LOOKUP_SANITIZE_RE = re.compile(r"[^0-9a-z]+")
_EXPLICIT_IMAGE_SPLIT_RE = re.compile(r"[;\n|]+")
_UPLOAD_CACHE_PATH = Path.home() / ".zeitshop_converter" / "wix_media_cache.json"
_UPLOAD_TIMEOUT_SECONDS = 180.0
_UPLOAD_POLL_SECONDS = 1.5
_WIX_UPLOAD_CONNECTIVITY_TIMEOUT_SECONDS = 5.0
_WIX_UPLOAD_OFFLINE_MESSAGE = "Internet nötig um Bilder automatisch hochzuladen"

ProgressCallback = Callable[[str], None]


class WixUploadConnectivityError(ConnectionError):
    """Raised when a Wix media upload is requested without internet connectivity."""


def ensure_wix_upload_connectivity() -> None:
    """Fail fast when Wix uploads are requested without internet access."""

    try:
        with socket.create_connection(
            ("www.wixapis.com", 443),
            timeout=_WIX_UPLOAD_CONNECTIVITY_TIMEOUT_SECONDS,
        ):
            pass
    except OSError as exc:
        raise WixUploadConnectivityError(_WIX_UPLOAD_OFFLINE_MESSAGE) from exc


def _is_remote_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_supported_image(path: Path) -> bool:
    return path.suffix.casefold() in _SUPPORTED_EXTENSIONS


def _sanitize_lookup_key(value: str | None) -> str:
    return _LOOKUP_SANITIZE_RE.sub("", normalize_text(value).casefold())


def _split_explicit_refs(raw_value: str | None) -> list[str]:
    text = "" if raw_value is None else str(raw_value).strip()
    if not text:
        return []
    parts = [
        normalize_text(part)
        for part in _EXPLICIT_IMAGE_SPLIT_RE.split(text)
    ]
    return [part for part in parts if part]


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _display_name(result_handle: str, result_name: str, index: int, total: int) -> str:
    base = result_name or result_handle or "Produkt"
    if total <= 1:
        return base
    return f"{base} ({index}/{total})"


class ImageLibrary:
    """Search local directories for product images by file name or stem."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = roots
        self._paths: list[Path] = []
        self._by_name: dict[str, list[Path]] = {}
        self._by_stem: dict[str, list[Path]] = {}
        self._by_sanitized_stem: dict[str, list[Path]] = {}
        self._lookup_cache: dict[str, list[Path]] = {}

        seen_roots: set[str] = set()
        for root in roots:
            resolved_root = root.expanduser().resolve()
            key = str(resolved_root)
            if key in seen_roots or not resolved_root.exists() or not resolved_root.is_dir():
                continue
            seen_roots.add(key)
            for path in resolved_root.rglob("*"):
                if not path.is_file() or not _is_supported_image(path):
                    continue
                self._paths.append(path)
                self._by_name.setdefault(path.name.casefold(), []).append(path)
                self._by_stem.setdefault(path.stem.casefold(), []).append(path)
                sanitized = _sanitize_lookup_key(path.stem)
                if sanitized:
                    self._by_sanitized_stem.setdefault(sanitized, []).append(path)

    def find_matches(self, value: str | None) -> list[Path]:
        token = normalize_text(value)
        if not token:
            return []
        cached = self._lookup_cache.get(token)
        if cached is not None:
            return list(cached)

        matches: list[Path] = []
        lower_token = token.casefold()
        matches.extend(self._by_name.get(lower_token, []))
        matches.extend(self._by_stem.get(lower_token, []))

        sanitized = _sanitize_lookup_key(token)
        if sanitized:
            matches.extend(self._by_sanitized_stem.get(sanitized, []))

        for path in self._paths:
            stem = path.stem.casefold()
            if stem.startswith(f"{lower_token}_") or stem.startswith(f"{lower_token}-"):
                matches.append(path)

        deduped = _dedupe_paths(matches)
        self._lookup_cache[token] = deduped
        return list(deduped)


class WixMediaClient:
    """Upload local files to Wix Media Manager and return stable image URLs."""

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

    def upload_image(self, path: Path) -> str:
        resolved_path = path.expanduser().resolve()
        cache_key = self._cache_key(resolved_path)
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            cached_url = normalize_text(cached.get("url"))
            if cached_url:
                return cached_url

        self._ensure_connectivity()

        mime_type = mimetypes.guess_type(resolved_path.name)[0] or "application/octet-stream"
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
        file_id = file_id or self._extract_file_id_from_upload_url(upload_url)

        if not file_id:
            raise ValueError("Could not determine the Wix file ID after upload.")

        descriptor = self._wait_for_ready(file_id)
        media_url = self._extract_media_url(descriptor)
        if not media_url:
            raise ValueError(f"Wix file {file_id!r} did not return a public media URL.")

        self._cache[cache_key] = {
            "file_id": file_id,
            "url": media_url,
        }
        self._save_cache()
        return media_url

    def _ensure_connectivity(self) -> None:
        if self._connectivity_checked:
            return

        ensure_wix_upload_connectivity()
        self._connectivity_checked = True

    def _cache_key(self, path: Path) -> str:
        stat = path.stat()
        return "|".join(
            [
                self.site_id,
                str(path),
                str(stat.st_size),
                str(stat.st_mtime_ns),
            ]
        )

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

    def _extract_file_id_from_upload_url(self, upload_url: str) -> str:
        token = upload_url.rstrip("/").rsplit("/", 1)[-1]
        parts = token.split(".")
        if len(parts) < 2:
            return ""
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode(f"{payload}{padding}".encode("ascii"))
            data = json.loads(decoded.decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return ""

        raw_path = normalize_text(data.get("path"))
        if not raw_path:
            return ""
        return raw_path.rsplit("/", 1)[-1]

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
                raise ValueError(
                    f"Wix returned no usable processing status for file {file_id!r}."
                )

            time.sleep(_UPLOAD_POLL_SECONDS)

        raise TimeoutError(f"Wix did not finish processing {file_id!r} within the timeout.")

    def _report_progress(self, message: str) -> None:
        if self.progress_callback is None:
            return
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

        thumbnail_url = normalize_text(descriptor.get("thumbnailUrl"))
        if thumbnail_url:
            return thumbnail_url
        return ""

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
        except HTTPError as exc:  # pragma: no cover - network error path
            details = exc.read().decode("utf-8", errors="replace")
            raise ValueError(
                f"Wix upload failed with HTTP {exc.code}: {details or exc.reason}"
            ) from exc
        except URLError as exc:  # pragma: no cover - network error path
            raise ValueError(f"Wix upload failed: {exc.reason}") from exc

    def _request_json(
        self,
        method: str,
        url: str,
        body: dict[str, object] | None = None,
        authenticated: bool = False,
    ) -> dict[str, object]:
        body_bytes = None
        if body is not None:
            body_bytes = json.dumps(body).encode("utf-8")

        auth_attempts = (False, True) if authenticated else (False,)
        last_error: Exception | None = None

        for use_bearer in auth_attempts:
            headers = {
                "Accept": "application/json",
            }
            if body_bytes is not None:
                headers["Content-Type"] = "application/json"
            if authenticated:
                headers["Authorization"] = (
                    f"Bearer {self.api_key}" if use_bearer else self.api_key
                )
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
                raise ValueError(
                    f"Wix API request failed with HTTP {exc.code}: {details or exc.reason}"
                ) from exc
            except URLError as exc:
                last_error = exc
                raise ValueError(f"Wix API request failed: {exc.reason}") from exc

        if last_error is not None:
            raise ValueError(str(last_error))
        return {}


def _build_image_roots(options: ImageMigrationOptions, source_file: Path) -> list[Path]:
    roots: list[Path] = []
    configured_dir = normalize_text(options.image_directory)
    if configured_dir:
        roots.append(Path(configured_dir).expanduser().resolve())
    roots.append(source_file.parent)

    result: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        result.append(root)
    return result


def _resolve_explicit_local_path(image_ref: str, search_roots: list[Path], library: ImageLibrary) -> Path | None:
    candidate = Path(image_ref).expanduser()
    if candidate.is_absolute() and candidate.exists() and candidate.is_file():
        return candidate

    for root in search_roots:
        resolved = root / image_ref
        if resolved.exists() and resolved.is_file():
            return resolved

    matches = library.find_matches(image_ref)
    return matches[0] if matches else None


def _collect_media_urls(
    result_source: Mapping[str, str],
    search_roots: list[Path],
    library: ImageLibrary,
    uploader: WixMediaClient | None,
    source_row: int,
) -> tuple[list[str], list[ValidationIssue]]:
    source = dict(result_source)
    issues: list[ValidationIssue] = []
    urls: list[str] = []

    explicit_refs = _split_explicit_refs(source.get("Bild"))
    explicit_urls: list[str] = []
    local_paths: list[Path] = []

    for image_ref in explicit_refs:
        if _is_remote_url(image_ref):
            explicit_urls.append(image_ref)
            continue

        local_path = _resolve_explicit_local_path(image_ref, search_roots, library)
        if local_path is None:
            issues.append(
                ValidationIssue(
                    source_row=source_row,
                    field="Bild",
                    severity=Severity.WARNING,
                    message=f"Image reference could not be resolved: '{image_ref}'.",
                )
            )
            continue

        if not _is_supported_image(local_path):
            issues.append(
                ValidationIssue(
                    source_row=source_row,
                    field="Bild",
                    severity=Severity.WARNING,
                    message=f"Unsupported image file type: '{local_path.name}'.",
                )
            )
            continue

        local_paths.append(local_path)

    if not explicit_refs:
        for fallback in (source.get("Artikel Nr"), source.get("Referenz")):
            local_paths.extend(library.find_matches(fallback))

    urls.extend(_dedupe_strings(explicit_urls))

    for path in _dedupe_paths(local_paths):
        if uploader is None:
            issues.append(
                ValidationIssue(
                    source_row=source_row,
                    field="media",
                    severity=Severity.WARNING,
                    message=(
                        f"Local image found but Wix upload is not configured: '{path.name}'. "
                        "Set a Wix site ID and API key to migrate local files automatically."
                    ),
                )
            )
            continue

        try:
            urls.append(uploader.upload_image(path))
        except WixUploadConnectivityError:
            raise
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    source_row=source_row,
                    field="media",
                    severity=Severity.WARNING,
                    message=f"Failed to upload image '{path.name}' to Wix: {exc}",
                )
            )

    return _dedupe_strings(urls), issues


def _build_media_row(header: list[str], handle: str, media_url: str, alt_text: str) -> dict[str, str]:
    row = {column: "" for column in header}
    row["handle"] = handle
    row["fieldType"] = "MEDIA"
    row["media"] = media_url
    if "mediaAltText" in row:
        row["mediaAltText"] = alt_text
    return row


def attach_media_rows(
    batch: ConversionBatch,
    options: ImageMigrationOptions,
    source_file: str | Path,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """Resolve product media and append Wix MEDIA rows to the batch in place."""

    if not options.enabled:
        return
    if "media" not in batch.header:
        raise ValueError("Template CSV is missing the 'media' column required for image migration.")

    source_path = Path(source_file).expanduser().resolve()
    search_roots = _build_image_roots(options, source_path)
    library = ImageLibrary(search_roots)

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
    for row_index, result in enumerate(batch.results, start=1):
        name = normalize_text(result.wix_row.get("name"))
        handle = normalize_text(result.wix_row.get("handle"))
        if progress_callback is not None:
            progress_callback(f"Bilder {row_index}/{total}: {_display_name(handle, name, 1, 1)}")

        media_urls, issues = _collect_media_urls(
            result_source=dict(result.source),
            search_roots=search_roots,
            library=library,
            uploader=uploader,
            source_row=result.source_row,
        )
        result.issues.extend(issues)

        media_rows = [
            _build_media_row(
                header=batch.header,
                handle=handle,
                media_url=media_url,
                alt_text=_display_name(handle, name, index, len(media_urls)),
            )
            for index, media_url in enumerate(media_urls, start=1)
        ]
        result.media_rows.extend(media_rows)
