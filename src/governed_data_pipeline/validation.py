"""Cell types, configured cross-field/date rules and reference checks.

This validator reports declared rule failures. Flat DQ reports remain useful
summaries; this interface supplies cell-level reasons to record gates.
"""

from dataclasses import dataclass
from datetime import date, datetime
import math
import numbers
import operator

import numpy as np
import pandas as pd

from .contracts import CleaningIssue
from .values import missing



TYPES = {"string", "category", "integer", "float", "boolean", "date", "timestamp"}
OPERATORS = {"le": operator.le, "lt": operator.lt, "ge": operator.ge,
             "gt": operator.gt, "eq": operator.eq, "ne": operator.ne}


@dataclass
class ValidationResult:
    issues: list
    batch_failures: list

    @property
    def passed(self):
        return not self.issues and not self.batch_failures


def validate_schema(schema):
    columns = schema.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise ValueError("Schema requires a nonempty columns mapping")
    key = schema.get("primary_key")
    if key not in columns or not columns[key].get("required"):
        raise ValueError("Primary key must be a required schema column")
    if "allow_extra_columns" in schema and type(schema["allow_extra_columns"]) is not bool:
        raise ValueError("allow_extra_columns must be boolean")
    for column, rules in columns.items():
        if not isinstance(column, str) or not column.isidentifier():
            raise ValueError(f"Invalid field name: {column!r}")
        if rules.get("dtype") not in TYPES:
            raise ValueError(f"Unsupported field type: {column}")
        for flag in ("required", "unique"):
            if flag in rules and type(rules[flag]) is not bool:
                raise ValueError(f"{flag} must be boolean for {column}")
        for bound in ("min", "max"):
            if bound in rules and (
                rules["dtype"] not in {"integer", "float"}
                or isinstance(rules[bound], bool)
                or not isinstance(rules[bound], numbers.Real)
                or not math.isfinite(float(rules[bound]))
            ):
                raise ValueError(f"{bound} requires a finite numeric bound for {column}")
        if "min" in rules and "max" in rules and rules["min"] > rules["max"]:
            raise ValueError(f"Minimum exceeds maximum for {column}")
        if "boolean_tokens" in rules:
            tokens = rules["boolean_tokens"]
            if not isinstance(tokens, dict) or any(
                not isinstance(token, str) or not token or token != token.strip().casefold()
                or type(value) is not bool for token, value in tokens.items()
            ):
                raise ValueError(f"Boolean tokens require lowercase text keys and boolean values: {column}")
        if "allow_time_truncation" in rules and (
            rules["dtype"] != "date" or type(rules["allow_time_truncation"]) is not bool
        ):
            raise ValueError(f"allow_time_truncation requires a boolean on a date field: {column}")
        if "foreign_key" in rules:
            target = rules["foreign_key"]
            if not isinstance(target, str) or len(target.split(".")) != 2 or not all(
                part.isidentifier() for part in target.split(".")
            ):
                raise ValueError(f"Foreign key must use table.column: {column}")
    for rule in schema.get("comparisons", []):
        if rule.get("left") not in columns or rule.get("operator") not in OPERATORS:
            raise ValueError("Comparison requires a known left field and operator")
        if ("right" in rule) == ("value" in rule):
            raise ValueError("Comparison requires exactly one right field or literal value")
        if "right" in rule and rule["right"] not in columns:
            raise ValueError("Unknown comparison right field")
        if not isinstance(rule.get("code"), str) or not rule["code"]:
            raise ValueError("Comparison requires a reason code")
        if "when" in rule and (
            rule["when"].get("column") not in columns or "equals" not in rule["when"]
        ):
            raise ValueError("Conditional comparison requires a known field and equals value")


def matches_type(value, dtype):
    if dtype in {"string", "category"}:
        return isinstance(value, str)
    if dtype == "boolean":
        return isinstance(value, (bool, np.bool_))
    if dtype in {"integer", "float"}:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
            return False
        try:
            return math.isfinite(float(value)) and (
                dtype == "float" or int(value) == value
            )
        except (OverflowError, ValueError):
            return False
    if dtype == "date":
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).isoformat() == value
            except ValueError:
                return False
        if isinstance(value, (datetime, pd.Timestamp)):
            return value.hour == value.minute == value.second == value.microsecond == 0 and not getattr(value, "nanosecond", 0)
        return isinstance(value, date)
    if dtype == "timestamp":
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                return "T" in value and parsed is not None
            except ValueError:
                return False
        return isinstance(value, (datetime, pd.Timestamp))
    return False


def validate_fields(data, schema, references=None):
    validate_schema(schema)
    if not data.columns.is_unique:
        raise ValueError("Validation requires distinct column names")
    references = references or {}
    columns = schema["columns"]
    failures = required_column_failures(data, schema)
    if not schema.get("allow_extra_columns", False):
        failures.extend(f"unexpected_column:{column}" for column in data.columns if column not in columns)
    issues = []
    invalid_cells = set()

    def issue(position, column, code, value):
        issues.append(CleaningIssue(position, column, code, value))
        invalid_cells.add((position, column))

    for column, rules in columns.items():
        if column not in data.columns:
            continue
        values = data[column]
        for position, value in enumerate(values):
            if missing(value):
                if rules.get("required"):
                    issue(position, column, "missing_required", value)
                continue
            if not matches_type(value, rules["dtype"]):
                issue(position, column, "type_mismatch", value)
                continue
            if "allowed" in rules and value not in rules["allowed"]:
                issue(position, column, "value_not_allowed", value)
            if rules["dtype"] in {"integer", "float"}:
                if "min" in rules and value < rules["min"]:
                    issue(position, column, "below_min", value)
                if "max" in rules and value > rules["max"]:
                    issue(position, column, "above_max", value)
        if rules.get("unique") or column == schema["primary_key"]:
            present = values.map(lambda value: not missing(value))
            repeated = present & values.duplicated(keep=False)
            for position, flag in enumerate(repeated):
                if flag:
                    code = "duplicate_primary_key" if column == schema["primary_key"] else "duplicate_value"
                    issue(position, column, code, values.iloc[position])
        if "foreign_key" in rules:
            table, separator, foreign_column = rules["foreign_key"].partition(".")
            if not separator:
                raise ValueError("Foreign key must use table.column")
            reference = references.get(table)
            if reference is None or foreign_column not in reference.columns:
                failures.append(f"reference_unavailable:{table}.{foreign_column}")
            else:
                if reference[foreign_column].dropna().duplicated().any():
                    failures.append(f"reference_keys_not_unique:{table}.{foreign_column}")
                keys = set(reference[foreign_column].dropna())
                for position, value in enumerate(values):
                    if not missing(value) and (position, column) not in invalid_cells and value not in keys:
                        issue(position, column, "foreign_key_not_found", value)

    for rule in schema.get("comparisons", []):
        left = rule["left"]
        right = rule.get("right")
        condition = rule.get("when")
        required = [left] + ([right] if right else []) + ([condition["column"]] if condition else [])
        if any(column not in data.columns for column in required):
            # An absent optional field means missing values, just as a present
            # column of None does. Required absences are already batch failures
            # from required_column_failures; do not invent comparison values.
            continue
        for position in range(len(data)):
            if condition:
                condition_value = data[condition["column"]].iloc[position]
                if missing(condition_value) or condition_value != condition["equals"]:
                    continue
            if any((position, column) in invalid_cells for column in required):
                continue
            a = data[left].iloc[position]
            b = data[right].iloc[position] if right else rule["value"]
            if missing(a) or missing(b):
                continue
            try:
                if columns[left]["dtype"] in {"date", "timestamp"}:
                    a, b = pd.Timestamp(a), pd.Timestamp(b)
                passed = bool(OPERATORS[rule["operator"]](a, b))
            except (TypeError, ValueError):
                passed = False
            if not passed:
                issue(position, left, rule["code"], a)
    return ValidationResult(issues, list(dict.fromkeys(failures)))


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
