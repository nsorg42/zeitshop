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


@dataclass
class WixRowResult:
    """Final Wix row plus all issues detected for this source record."""

    source_row: int
    source: Mapping[str, str]
    wix_row: dict[str, str]
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
        return [result.wix_row for result in self.results if not result.has_errors]

    @property
    def error_rows(self) -> list[WixRowResult]:
        return [result for result in self.results if result.has_errors]

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if result.has_errors)

    @property
    def warning_count(self) -> int:
        return sum(1 for result in self.results if result.has_warnings)
