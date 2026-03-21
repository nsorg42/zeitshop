from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Issue severity used by validation and mapping diagnostics."""

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found while mapping or validating a row."""

    source_row: int
    field: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class DiamondRecord:
    """Canonicalized source row from a DIAMOND CSV file."""

    source_row: int
    data: Mapping[str, str]


@dataclass(frozen=True)
class ConversionOptions:
    """User-configurable behavior flags for conversion."""

    default_visible: bool = False
    numeric_inventory: bool = True
    handle_prefix: str = "ds-"
    image_migration: "ImageMigrationOptions | None" = None


@dataclass(frozen=True)
class ImageMigrationOptions:
    """Optional settings for resolving and migrating product images."""

    enabled: bool = False
    image_directory: str = ""
    export_embedded_images: bool = False
    export_directory: str = ""
    wix_site_id: str = ""
    wix_api_key: str = ""
    wix_file_path: str = "/zeitshop"


@dataclass
class WixRowResult:
    """Final Wix row plus all issues detected for this source record."""

    source_row: int
    source: Mapping[str, str]
    wix_row: dict[str, str]
    media_rows: list[dict[str, str]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == Severity.WARNING for issue in self.issues)


@dataclass
class ConversionBatch:
    """Container for all conversion results and convenience filters."""

    header: list[str]
    results: list[WixRowResult]

    @property
    def issue_rows(self) -> list[WixRowResult]:
        return [result for result in self.results if result.issues]

    @property
    def valid_product_rows(self) -> list[dict[str, str]]:
        return [result.wix_row for result in self.results if not result.has_errors]

    @property
    def valid_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for result in self.results:
            if result.has_errors:
                continue
            rows.append(result.wix_row)
            rows.extend(result.media_rows)
        return rows

    @property
    def error_rows(self) -> list[WixRowResult]:
        return [result for result in self.results if result.has_errors]

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if result.has_errors)

    @property
    def warning_count(self) -> int:
        return sum(1 for result in self.results if result.has_warnings)
