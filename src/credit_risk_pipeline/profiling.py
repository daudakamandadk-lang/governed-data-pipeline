"""Describe dataframe contents without cleaning, validating or loading them.

These functions preserve the Phase 1 profiling interface and can be used
without importing its schemas, synthetic generators or example runners.
"""

import pandas as pd


def profile_categorical(series, top_n=5):
    counts = series.value_counts(dropna=False)
    percentages = series.value_counts(dropna=False, normalize=True) * 100
    modes = series.mode()
    return {
        "mode": modes.iloc[0] if not modes.empty else None,
        "top_values": counts.head(top_n).to_dict(),
        "top_percentages": percentages.head(top_n).round(2).to_dict(),
    }


def profile_numeric(series):
    stats = series.describe()
    q1, q3 = stats["25%"], stats["75%"]
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    outlier_mask = (series < lower_bound) | (series > upper_bound)
    return {
        "count": int(stats["count"]),
        "mean": stats["mean"],
        "std": stats["std"],
        "min": stats["min"],
        "q1": q1,
        "median": stats["50%"],
        "q3": q3,
        "max": stats["max"],
        "zeros": int((series == 0).sum()),
        "negative": int((series < 0).sum()),
        "iqr": iqr,
        "lower_outlier_bound": lower_bound,
        "upper_outlier_bound": upper_bound,
        "outliers": int(outlier_mask.sum()),
    }


def profile_date(series, reference_date=None):
    valid_dates = series.dropna()
    profile = {
        "count": int(valid_dates.count()),
        "earliest": valid_dates.min() if not valid_dates.empty else None,
        "latest": valid_dates.max() if not valid_dates.empty else None,
        "range_days": (
            (valid_dates.max() - valid_dates.min()).days if not valid_dates.empty else None
        ),
    }
    if reference_date is not None:
        profile["future_dates"] = int((valid_dates > reference_date).sum())
    return profile


def profile_data(df, top_n=5, reference_date=None):
    if not df.columns.is_unique:
        raise ValueError("Profiling requires unique column names")
    profile = {
        "rows": len(df),
        "columns": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "fields": {},
    }
    for column in df.columns:
        series = df[column]
        field_profile = {
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "missing_pct": round(series.isna().mean() * 100, 2) if len(series) else 0.0,
            "unique": series.nunique(),
        }
        if pd.api.types.is_datetime64_any_dtype(series):
            field_profile["date"] = profile_date(series, reference_date=reference_date)
        elif pd.api.types.is_bool_dtype(series):
            field_profile["categorical"] = profile_categorical(series, top_n=top_n)
        elif pd.api.types.is_numeric_dtype(series):
            field_profile["numeric"] = profile_numeric(series)
        elif (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)
        ):
            field_profile["categorical"] = profile_categorical(series, top_n=top_n)
        profile["fields"][column] = field_profile
    return profile
