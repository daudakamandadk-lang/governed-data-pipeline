"""Learning cleaner for schema-guided, non-destructive field normalization."""

from .contracts import CleaningCorrection, CleaningIssue, CleaningResult
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import math
import numbers

import numpy as np
import pandas as pd








class CleaningEngine:
    def clean(self, data, schema=None, date_formats=None):
        if not data.columns.is_unique:
            raise ValueError("Cleaner requires unique column names")

        # Keep the original one-argument ID-cleaning call working for the first
        # lesson while allowing later lessons to pass an explicit table schema.
        if schema is None:
            if "applicant_id" not in data.columns:
                raise ValueError("Required column missing from input: applicant_id")
            rules_by_column = {"applicant_id": {"dtype": "string"}}
        else:
            rules_by_column = schema.get("columns")
            if not isinstance(rules_by_column, dict):
                raise ValueError("Schema must contain a columns mapping")

        date_formats = date_formats or {}
        supported_types = {
            "string", "category", "float", "integer", "date", "timestamp", "boolean"
        }
        for column, rules in rules_by_column.items():
            if "allow_time_truncation" in rules and (
                rules.get("dtype") != "date" or type(rules["allow_time_truncation"]) is not bool
            ):
                raise ValueError(f"allow_time_truncation requires a boolean on a date field: {column}")
            if column not in data.columns:
                continue
            dtype = rules.get("dtype")
            if dtype not in supported_types:
                raise ValueError(f"Unsupported cleaning dtype for {column}: {dtype!r}")
            if dtype in {"date", "timestamp"} and column not in date_formats:
                raise ValueError(
                    f"Date formats must be configured for date field: {column}"
                )

        cleaned = data.copy()
        corrections = []
        issues = []

        def write_correction(row_position, column, value, normalized, reason):
            column_position = cleaned.columns.get_loc(column)
            try:
                cleaned.iat[row_position, column_position] = normalized
            except (TypeError, ValueError):
                # Categorical and pandas string columns reject values outside
                # their vocabulary or type; object can hold any correction.
                cleaned.isetitem(
                    column_position,
                    cleaned.iloc[:, column_position].astype(object),
                )
                cleaned.iat[row_position, column_position] = normalized
            corrections.append(
                CleaningCorrection(
                    row_position=row_position,
                    column=column,
                    reason=reason,
                    original_value=value,
                    cleaned_value=normalized,
                )
            )

        for column, rules in rules_by_column.items():
            if column not in data.columns:
                continue

            dtype = rules["dtype"]
            column_position = data.columns.get_loc(column)
            allowed = rules.get("allowed")
            allowed_values = set(allowed) if allowed is not None else None

            for row_position, value in enumerate(data.iloc[:, column_position]):
                if pd.api.types.is_scalar(value) and pd.isna(value):
                    continue
                if isinstance(value, str) and not value.strip():
                    write_correction(
                        row_position, column, value, pd.NA, "blank_to_missing"
                    )
                    continue

                if dtype in {"string", "category"}:
                    if not isinstance(value, str):
                        continue
                    normalized = value.strip()
                    if normalized != value:
                        write_correction(
                            row_position, column, value, normalized, "trim_whitespace"
                        )
                    if (
                        dtype == "category"
                        and allowed_values is not None
                        and normalized not in allowed_values
                    ):
                        issues.append(
                            CleaningIssue(
                                row_position, column, "value_not_allowed", normalized
                            )
                        )

                elif dtype in {"float", "integer"}:
                    if isinstance(value, (bool, np.bool_)):
                        issues.append(
                            CleaningIssue(
                                row_position, column, "numeric_type_mismatch", value
                            )
                        )
                        continue

                    source_value = value.strip() if isinstance(value, str) else value
                    try:
                        if dtype == "integer":
                            decimal_value = Decimal(str(source_value))
                            if (
                                not decimal_value.is_finite()
                                or decimal_value != decimal_value.to_integral_value()
                            ):
                                raise ValueError("Value is not a finite integer")
                            normalized = int(decimal_value)
                        else:
                            parsed = pd.to_numeric(source_value, errors="raise")
                            normalized = float(parsed)
                            if not math.isfinite(normalized):
                                raise ValueError("Numeric values must be finite")
                    except (InvalidOperation, TypeError, ValueError, OverflowError):
                        issues.append(
                            CleaningIssue(
                                row_position, column, "numeric_parse_failed", value
                            )
                        )
                        continue

                    needs_conversion = isinstance(value, str) or (
                        dtype == "integer" and not isinstance(value, numbers.Integral)
                    )
                    if needs_conversion:
                        write_correction(
                            row_position, column, value, normalized, "parse_numeric"
                        )

                elif dtype == "boolean":
                    if isinstance(value, (bool, np.bool_)):
                        continue
                    # Source contracts may provide additional exact text tokens.
                    tokens = rules.get("boolean_tokens", {"true": True, "false": False})
                    if not isinstance(tokens, dict) or any(type(item) is not bool for item in tokens.values()):
                        raise ValueError(f"Boolean tokens must map text to booleans: {column}")
                    token = value.strip().casefold() if isinstance(value, str) else None
                    if token is not None and token in tokens:
                        write_correction(row_position, column, value, tokens[token], "parse_boolean")
                    else:
                        issues.append(CleaningIssue(row_position, column, "boolean_parse_failed", value))

                elif dtype in {"date", "timestamp"}:
                    if isinstance(value, (date, datetime, pd.Timestamp)):
                        parsed_dates = [pd.Timestamp(value)]
                    elif isinstance(value, str):
                        source_value = value.strip()
                        formats = date_formats[column]
                        if isinstance(formats, str):
                            formats = [formats]
                        parsed_dates = []
                        for date_format in formats:
                            try:
                                parsed = pd.to_datetime(
                                    source_value,
                                    format=date_format,
                                    errors="raise",
                                )
                                # Literal text can parse to NaT even with
                                # errors="raise"; it is not a usable date.
                                if not pd.isna(parsed):
                                    parsed_dates.append(parsed)
                            except (TypeError, ValueError):
                                continue
                    else:
                        issues.append(
                            CleaningIssue(row_position, column, "date_parse_failed", value)
                        )
                        continue

                    distinct_dates = {parsed.isoformat() for parsed in parsed_dates}
                    if len(distinct_dates) > 1:
                        issues.append(
                            CleaningIssue(row_position, column, "ambiguous_date", value)
                        )
                        continue
                    if not parsed_dates:
                        issues.append(
                            CleaningIssue(row_position, column, "date_parse_failed", value)
                        )
                        continue

                    parsed_date = parsed_dates[0]
                    has_time = any((parsed_date.hour, parsed_date.minute, parsed_date.second,
                                    parsed_date.microsecond, parsed_date.nanosecond))
                    if dtype == "date" and has_time and not rules.get("allow_time_truncation", False):
                        issues.append(
                            CleaningIssue(row_position, column, "date_time_truncation_blocked", value)
                        )
                        continue
                    normalized = (
                        parsed_date.strftime("%Y-%m-%d")
                        if dtype == "date"
                        else parsed_date.isoformat()
                    )
                    if normalized != value:
                        write_correction(
                            row_position, column, value, normalized, "normalize_date"
                        )

        return CleaningResult(
            data=cleaned,
            corrected_cells=len(corrections),
            corrections=corrections,
            issues=issues,
        )
