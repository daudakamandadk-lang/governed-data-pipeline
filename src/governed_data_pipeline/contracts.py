"""Shared value contracts; engines do not import one another for result types."""

from dataclasses import dataclass, field
import pandas as pd


@dataclass(frozen=True)
class CleaningCorrection:
    row_position: int
    column: str
    reason: str
    original_value: object
    cleaned_value: object


@dataclass(frozen=True)
class CleaningIssue:
    row_position: int
    column: str
    code: str
    value: object


@dataclass
class CleaningResult:
    data: pd.DataFrame
    corrected_cells: int
    corrections: list[CleaningCorrection] = field(default_factory=list)
    issues: list[CleaningIssue] = field(default_factory=list)
