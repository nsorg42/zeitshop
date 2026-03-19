from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationIssue:
    source_row: int
    field: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class DiamondRecord:
    source_row: int
    data: Mapping[str, str]


@dataclass(frozen=True)
class ConversionOptions:
    default_visible: bool = False
    numeric_inventory: bool = True
    handle_prefix: str = "ds-"


@dataclass
class WixRowResult:
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
    header: list[str]
    results: list[WixRowResult]

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
