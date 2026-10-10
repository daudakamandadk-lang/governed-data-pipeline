"""Record dispositions and batch quality gates for cleaned learning batches.

classify_records() decides, per record, whether it passes, was corrected, is
quarantined or is rejected, always with explicit reasons. Cleaner issue codes
appear as ``code:column``; schema checks add their own reasons. The batch gate
summarizes those dispositions against stop and warn thresholds. Nothing is
removed here: callers use the dispositions to decide which rows to load.
Rejection is reserved for records without a usable primary key.
"""

from dataclasses import dataclass, field
import math

import pandas as pd


DISPOSITION_ORDER = ("pass", "corrected", "quarantine", "reject")
PROCEEDING_DISPOSITIONS = ("pass", "corrected")


@dataclass(frozen=True)
class RecordDisposition:
    row_position: int
    index: object
    disposition: str
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GateThresholds:
    max_reject_rate: float = 0.0
    max_quarantine_rate: float = 0.0
    warn_quarantine_rate: float | None = None


@dataclass(frozen=True)
class GateResult:
    outcome: str
    total: int
    counts: dict
    rates: dict
    reasons: list[str] = field(default_factory=list)
    proceeding: int = 0


def _is_missing(value):
    if isinstance(value, str):
        # A whitespace-only cell counts as missing, matching the cleaner.
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _python_scalar(value):
    if hasattr(value, "item"):
        return value.item()
    return value


def classify_records(data, schema, corrections=(), issues=()):
    """Assign a disposition and reasons to every row of a cleaned batch."""
    if not data.columns.is_unique:
        raise ValueError("Classification requires unique column names")
    columns = schema.get("columns")
    primary_key = schema.get("primary_key")
    if not isinstance(columns, dict):
        raise ValueError("Schema must contain a columns mapping")
    if not isinstance(primary_key, str):
        raise ValueError("Schema must define a primary key")

    issue_reasons_by_row = {}
    issue_columns_by_row = {}
    for issue in issues:
        issue_reasons_by_row.setdefault(issue.row_position, []).append(
            f"{issue.code}:{issue.column}"
        )
        issue_columns_by_row.setdefault(issue.row_position, set()).add(issue.column)
    corrected_rows = {correction.row_position for correction in corrections}

    duplicate_positions = set()
    if primary_key in data.columns:
        present_keys = data[primary_key]
        repeated = present_keys.notna() & present_keys.duplicated(keep=False)
        duplicate_positions = {
            position for position, flag in enumerate(repeated) if flag
        }

    numeric_views = {}
    for column, rules in columns.items():
        if column in data.columns and ("min" in rules or "max" in rules):
            numeric_views[column] = pd.to_numeric(
                data[column], errors="coerce"
            )

    column_positions = {
        column: data.columns.get_loc(column)
        for column in columns
        if column in data.columns
    }

    dispositions = []
    for row_position in range(len(data)):
        reasons = []
        pk_missing = primary_key not in column_positions or _is_missing(
            data.iat[row_position, column_positions[primary_key]]
        )
        if pk_missing:
            reasons.append("missing_primary_key")

        reasons.extend(issue_reasons_by_row.get(row_position, ()))
        columns_with_issue = issue_columns_by_row.get(row_position, set())

        for column, rules in columns.items():
            if column not in column_positions:
                # An absent column is a batch-level failure reported by
                # run_dq_checks; per-row checks only evaluate present data.
                continue
            value = data.iat[row_position, column_positions[column]]
            if _is_missing(value):
                if rules.get("required") and column != primary_key:
                    reasons.append(f"missing_required:{column}")
                continue

            allowed = rules.get("allowed")
            if allowed is not None and value not in allowed:
                reasons.append(f"value_not_allowed:{column}")

            if column in numeric_views:
                numeric_value = numeric_views[column].iat[row_position]
                if pd.isna(numeric_value):
                    if column not in columns_with_issue:
                        # The cleaner records parse failures; otherwise this
                        # cell was never convertible to a number.
                        reasons.append(f"invalid_number:{column}")
                elif not math.isfinite(float(numeric_value)):
                    reasons.append(f"nonfinite:{column}")
                else:
                    if "min" in rules and numeric_value < rules["min"]:
                        reasons.append(f"below_min:{column}")
                    if "max" in rules and numeric_value > rules["max"]:
                        reasons.append(f"above_max:{column}")

        if not pk_missing and row_position in duplicate_positions:
            reasons.append("duplicate_primary_key")

        # Later duplicates of one reason (cleaner plus schema check) collapse.
        reasons = list(dict.fromkeys(reasons))

        if "missing_primary_key" in reasons:
            disposition = "reject"
        elif reasons:
            disposition = "quarantine"
        elif row_position in corrected_rows:
            disposition = "corrected"
        else:
            disposition = "pass"

        dispositions.append(
            RecordDisposition(
                row_position=row_position,
                index=data.index[row_position],
                disposition=disposition,
                reasons=reasons,
            )
        )

    return dispositions


def required_column_failures(data, schema):
    """Report absent required columns once for the batch, including empty input."""
    columns = schema.get("columns")
    if not isinstance(columns, dict):
        raise ValueError("Schema must contain a columns mapping")
    return [
        f"missing_required_column:{column}"
        for column, rules in columns.items()
        if rules.get("required") and column not in data.columns
    ]


def evaluate_gate(dispositions, thresholds=None, *, batch_failures=()):
    """Apply batch failures and record rates to a pass, warn or stop decision.

    Callers supply required_column_failures(data, schema) alongside the row
    dispositions. A structural failure always stops the batch, independent
    of its row count or configured reject/quarantine thresholds.
    """
    thresholds = thresholds or GateThresholds()
    for name in ("max_reject_rate", "max_quarantine_rate", "warn_quarantine_rate"):
        value = getattr(thresholds, name)
        if value is None and name == "warn_quarantine_rate":
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            raise ValueError(f"Threshold {name} must be between 0 and 1")
    if thresholds.warn_quarantine_rate is not None and thresholds.warn_quarantine_rate > thresholds.max_quarantine_rate:
        raise ValueError("Warning threshold cannot exceed the quarantine stop threshold")

    counts = {name: 0 for name in DISPOSITION_ORDER}
    for record in dispositions:
        if record.disposition not in counts:
            raise ValueError(f"Unknown disposition: {record.disposition!r}")
        counts[record.disposition] += 1

    total = len(dispositions)
    rates = {
        name: (counts[name] / total if total else 0.0)
        for name in DISPOSITION_ORDER
    }

    reasons = list(dict.fromkeys(batch_failures))
    outcome = "stop" if reasons else "pass"
    if rates["reject"] > thresholds.max_reject_rate:
        outcome = "stop"
        reasons.append(
            f"reject rate {rates['reject']:.1%} exceeds maximum "
            f"{thresholds.max_reject_rate:.1%}"
        )
    if rates["quarantine"] > thresholds.max_quarantine_rate:
        outcome = "stop"
        reasons.append(
            f"quarantine rate {rates['quarantine']:.1%} exceeds maximum "
            f"{thresholds.max_quarantine_rate:.1%}"
        )
    elif (
        outcome != "stop"
        and thresholds.warn_quarantine_rate is not None
        and rates["quarantine"] > thresholds.warn_quarantine_rate
    ):
        outcome = "warn"
        reasons.append(
            f"quarantine rate {rates['quarantine']:.1%} exceeds warning level "
            f"{thresholds.warn_quarantine_rate:.1%}"
        )

    return GateResult(
        outcome=outcome,
        total=total,
        counts=counts,
        rates=rates,
        reasons=reasons,
        proceeding=counts["pass"] + counts["corrected"],
    )


# Prefer the explicit name for new callers; existing orchestration keeps its API.
evaluate_record_gate = evaluate_gate
