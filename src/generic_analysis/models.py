"""Small in-memory contracts; results can contain sensitive aggregates."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NextStep:
    action: str
    columns: tuple[str, ...]
    reason: str


@dataclass
class AnalysisResult:
    row_count: int
    roles: dict[str, str]
    context: dict[str, Any] = field(default_factory=dict)
    descriptive: dict[str, dict[str, Any]] = field(default_factory=dict)
    distributions: dict[str, dict[str, Any]] = field(default_factory=dict)
    correlations: list[dict[str, Any]] = field(default_factory=list)
    groups: list[dict[str, Any]] = field(default_factory=list)
    time_hooks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[NextStep] = field(default_factory=list)
