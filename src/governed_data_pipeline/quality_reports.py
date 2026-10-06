"""Honest per-field evidence; descriptive counts do not certify source accuracy."""
from collections import Counter

from .values import missing
from .profiling import profile_data


def validation_scorecard(data, schema, result):
    """Summarize reported cell failures without confusing field scores with rows."""
    fields = {}
    affected = set()
    for column, rules in schema["columns"].items():
        issues = [issue for issue in result.issues if issue.column == column]
        positions = {issue.row_position for issue in issues}
        affected.update(positions)
        present = column in data.columns
        fields[column] = {
            "expected_type": rules["dtype"],
            "required": rules.get("required", False),
            "present_column": present,
            "missing_values": sum(missing(value) for value in data[column]) if present else len(data),
            "reported_failed_rows": len(positions),
            "issues_by_code": dict(sorted(Counter(issue.code for issue in issues).items())),
            "assessment": "assessed" if present else "required_column_missing" if rules.get("required") else "not_present_optional",
        }
    return {
        "rows": len(data),
        "fields": fields,
        "reported_failed_rows": len(affected),
        "rows_without_reported_cell_issues": len(data) - len(affected),
        "batch_failures": list(result.batch_failures),
        "contract_passed": bool(result.passed),
        "source_accuracy": "not_assessed",
        "issue_counts_are": "cell failures; a row can fail more than one field or rule",
    }


def table_evidence(original, cleaned, schema, before, after, dispositions=(), gate=None):
    """Build a JSON-convertible before/after record for one processed table."""
    result = {
        "profile_before": profile_data(original),
        "profile_after": profile_data(cleaned.data),
        "validation_before": validation_scorecard(original, schema, before),
        "validation_after": validation_scorecard(cleaned.data, schema, after),
        "corrected_cells": cleaned.corrected_cells,
        "cleaning_issues_by_code": dict(sorted(Counter(issue.code for issue in cleaned.issues).items())),
        "record_dispositions": dict(sorted(Counter(item.disposition for item in dispositions).items())),
    }
    if gate is not None:
        from dataclasses import asdict
        result["gate"] = asdict(gate)
    return result
