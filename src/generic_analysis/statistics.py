"""Descriptive checks only: no significance tests or causal inference."""

import numpy as np
import pandas as pd


def numeric_values(series: pd.Series) -> pd.Series:
    # Non-finite observations are reported separately and excluded from calculations.
    return series.astype(float).replace([np.inf, -np.inf], np.nan).dropna()


def describe_measure(series: pd.Series) -> tuple[dict, dict]:
    values = numeric_values(series)
    summary = {"count": len(values), "missing": int(series.isna().sum()),
               "non_finite": int(np.isinf(series.astype(float)).sum())}
    for key, value in values.describe().items():
        summary[key] = float(value) if pd.notna(value) else None
    variance = values.var()
    summary["variance"] = float(variance) if pd.notna(variance) else None
    skew = values.skew() if len(values) >= 3 and values.nunique() > 1 else np.nan
    return summary, {"skew": float(skew) if pd.notna(skew) else None,
                     "constant": len(values) > 0 and values.nunique() == 1}


def detect_correlations(data: pd.DataFrame, measures: list[str]) -> list[dict]:
    findings = []
    for i, left in enumerate(measures):
        for right in measures[i + 1:]:
            pair = data[[left, right]].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
            if len(pair) < 3 or any(pair[c].nunique() < 2 for c in pair):
                continue
            coefficient = pair[left].corr(pair[right])
            if pd.notna(coefficient):
                findings.append({"columns": (left, right), "method": "pearson",
                                 "coefficient": float(coefficient), "count": len(pair)})
    return findings


def compare_groups(data: pd.DataFrame, category: str, measure: str) -> dict:
    frame = pd.DataFrame({"group": data[category], "value": data[measure].astype(float)})
    frame["value"] = frame["value"].replace([np.inf, -np.inf], np.nan)
    summary = frame.groupby("group", observed=True, dropna=True)["value"].agg(["count", "mean", "median"])
    return {"columns": (category, measure), "summary": summary,
            "excluded_missing_group": int(frame["group"].isna().sum())}
