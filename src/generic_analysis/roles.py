"""Dtypes give tentative roles; caller metadata supplies meaning."""

import pandas as pd
from pandas.api.types import (
    is_bool_dtype, is_complex_dtype, is_datetime64_any_dtype, is_numeric_dtype,
)

ROLES = {"identifier", "measure", "category", "time", "ignore"}


def infer_roles(data: pd.DataFrame, metadata: dict | None = None) -> dict[str, str]:
    if not data.columns.is_unique or not all(isinstance(c, str) for c in data.columns):
        raise ValueError("Columns must have unique string names.")
    columns = (metadata or {}).get("columns", {})
    unknown = set(columns) - set(data.columns)
    if unknown:
        raise ValueError(f"Metadata refers to unknown columns: {sorted(unknown)}")
    roles = {}
    for name, series in data.items():
        role = columns.get(name, {}).get("role")
        if role is None:
            if is_datetime64_any_dtype(series.dtype):
                role = "time"
            elif is_bool_dtype(series.dtype) or not is_numeric_dtype(series.dtype):
                role = "category"
            else:
                role = "measure"
        if role not in ROLES:
            raise ValueError(f"Unsupported role for {name}: {role}")
        if role == "measure" and (not is_numeric_dtype(series.dtype) or is_bool_dtype(series.dtype) or is_complex_dtype(series.dtype)):
            raise ValueError(f"Measure {name} requires a numeric dtype.")
        if role == "time" and not is_datetime64_any_dtype(series.dtype):
            raise ValueError(f"Time column {name} requires a datetime dtype; parse explicitly.")
        roles[name] = role
    return roles
