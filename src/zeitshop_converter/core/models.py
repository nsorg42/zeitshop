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
    source_format: str = "diamond_csv"


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


@dataclass(frozen=True)
class InventoryUpdateResult:
    """One Wix product row after matching against current DIAMOND inventory."""

    source_row: int
    wix_row: dict[str, str]
    original_inventory: str
    updated_inventory: str
    matched: bool
    changed: bool
    set_to_zero: bool = False
    is_new_product: bool = False
    source_kind: str = "wix"

    @property
    def has_errors(self) -> bool:
        return False

    @property
    def has_warnings(self) -> bool:
        return False


@dataclass
class InventoryUpdateIssueRow:
    """One issue found while preparing an inventory update."""

    source_row: int
    source: Mapping[str, str]
    issues: list[ValidationIssue] = field(default_factory=list)
    kind: str = "generic"

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == Severity.WARNING for issue in self.issues)


@dataclass
class InventoryUpdateBatch:
    """Container for a Wix inventory update export and preview rows."""

    header: list[str]
    rows: list[dict[str, str]]
    results: list[InventoryUpdateResult]
    issue_rows: list[InventoryUpdateIssueRow] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return sum(1 for result in self.results if result.changed)

    @property
    def matched_count(self) -> int:
        return sum(1 for result in self.results if result.matched)

    @property
    def set_to_zero_count(self) -> int:
        return sum(1 for result in self.results if result.set_to_zero)

    @property
    def new_product_count(self) -> int:
        return sum(1 for result in self.results if result.is_new_product)

    @property
    def unmatched_diamond_count(self) -> int:
        return sum(1 for result in self.issue_rows if result.kind == "unmatched_diamond")

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.issue_rows if result.has_errors)

    @property
    def warning_count(self) -> int:
        return sum(1 for result in self.issue_rows if result.has_warnings)

    @property
    def has_blocking_errors(self) -> bool:
        return self.error_count > 0
