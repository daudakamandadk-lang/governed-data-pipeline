"""Independent band transformation and reconciliation result contracts."""
from dataclasses import dataclass
import math
import numbers
import pandas as pd

@dataclass(frozen=True)
class BandRule:
    low: float | None  # Inclusive lower bound; None means no lower bound.
    high: float | None  # Exclusive upper bound; None means no upper bound.
    label: str

    def __post_init__(self):
        for name, bound in (("low", self.low), ("high", self.high)):
            if bound is None:
                continue
            try:
                valid = (not isinstance(bound, bool)
                         and isinstance(bound, numbers.Real)
                         and math.isfinite(float(bound)))
            except (OverflowError, TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError(f"Band {name} must be a finite nonboolean number or None")
        if self.low is not None and self.high is not None and self.low >= self.high:
            raise ValueError("Band low must be less than high")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("Band label must be nonempty text")

    def contains(self, value):
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            return False
        try:
            if not math.isfinite(float(value)):
                return False
        except (OverflowError, TypeError, ValueError):
            return False
        if self.low is not None and value < self.low:
            return False
        if self.high is not None and value >= self.high:
            return False
        return True


@dataclass(frozen=True)
class ReconciliationCheck:
    name: str
    expected: object
    actual: object
    passed: bool


@dataclass(frozen=True)
class ReconciliationReport:
    checks: list[ReconciliationCheck]

    @property
    def passed(self):
        return all(check.passed for check in self.checks)


class BandTransformer:
    def __init__(self, source_column, derived_column, rules):
        if not source_column or not derived_column:
            raise ValueError("Source and derived column names are required")
        if source_column == derived_column:
            raise ValueError("A derived column must have its own name")
        rules = list(rules)
        if not rules:
            raise ValueError("At least one band rule is required")
        if any(not isinstance(rule, BandRule) for rule in rules):
            raise ValueError("Each band must be a BandRule")
        ordered = sorted(rules, key=lambda rule: -math.inf if rule.low is None else rule.low)
        for previous, current in zip(ordered, ordered[1:]):
            # High is exclusive, so adjacent bands may share a boundary.
            if previous.high is None or current.low is None or current.low < previous.high:
                raise ValueError("Band rules must not overlap")
        self.source_column = source_column
        self.derived_column = derived_column
        self.rules = list(rules)

    def _label(self, value):
        # Missing, nonnumeric and nonfinite values stay visible as missing
        # bands; earlier stages keep the original value for inspection.
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return pd.NA
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            return pd.NA
        if not math.isfinite(float(value)):
            return pd.NA
        for rule in self.rules:
            if rule.contains(float(value)):
                return rule.label
        return pd.NA

    def transform(self, data):
        """Return a copy of data with one derived band column."""
        if not isinstance(data, pd.DataFrame):
            raise ValueError("transform expects a pandas DataFrame")
        if self.source_column not in data.columns:
            raise ValueError(
                f"Required column missing from input: {self.source_column}"
            )
        if self.derived_column in data.columns:
            raise ValueError("Transformation cannot overwrite an existing column")
        transformed = data.copy()
        # Assigning a list is positional, so repeated index labels stay safe.
        transformed[self.derived_column] = [
            self._label(value) for value in data[self.source_column]
        ]
        return transformed


def _validate_identifier(name, kind):
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError(f"Invalid SQL {kind} name: {name!r}")
    return name
