"""Original field-level DQ summaries, retained for API compatibility.

Typed contracts and row reasons belong to validation.validate_fields.
These scores count field checks; they are not accepted-row rates.
"""
import math
import numbers
import numpy as np
import pandas as pd
from .values import missing


def field(required=True, unique=False, min_value=None, max_value=None, allowed=None):
    rules = {"required": required, "unique": unique}
    for key, value in (("min", min_value), ("max", max_value), ("allowed", allowed)):
        if value is not None:
            rules[key] = value
    return rules


def check_completeness(df, schema):
    results = {}
    for column, rules in schema.items():
        if rules.get("required", False):
            if column not in df:
                results[column] = {"missing": len(df), "passed": False, "missing_column": True}
            else:
                count = sum(missing(value) for value in df[column])
                results[column] = {"missing": count, "passed": count == 0}
    return results


def check_uniqueness(df, schema):
    results = {}
    for column, rules in schema.items():
        if rules.get("unique", False):
            if column not in df:
                results[column] = {"duplicates": 0, "passed": False, "missing_column": True}
            else:
                present = df[column].map(lambda value: not missing(value))
                count = int(df.loc[present, column].duplicated().sum())
                results[column] = {"duplicates": count, "passed": count == 0}
    return results


def _valid(value, rules):
    if missing(value):
        return True  # Completeness owns missingness.
    if "min" in rules or "max" in rules:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
            return False  # Judge the original value; cleaning owns conversion.
        if not math.isfinite(float(value)):
            return False
        if "min" in rules and value < rules["min"]:
            return False
        if "max" in rules and value > rules["max"]:
            return False
    return "allowed" not in rules or value in rules["allowed"]


def check_validity(df, schema):
    results = {}
    for column, rules in schema.items():
        if column not in df:
            has_rule = any(key in rules for key in ("min", "max", "allowed"))
            results[column] = {"invalid": 0, "passed": not has_rule, "missing_column": True}
        else:
            count = sum(not _valid(value, rules) for value in df[column])
            results[column] = {"invalid": count, "passed": count == 0}
    return results


def run_dq_checks(df, schema):
    if not isinstance(df, pd.DataFrame) or not df.columns.is_unique:
        raise ValueError("DQ summaries require a DataFrame with unique column names")
    return {"completeness": check_completeness(df, schema),
            "validity": check_validity(df, schema),
            "uniqueness": check_uniqueness(df, schema)}


def dimension_score(results):
    """Fraction of passed field checks; 1.0 on an empty dimension means no checks."""
    if not results:
        return 1.0
    return sum(bool(result["passed"]) for result in results.values()) / len(results)
