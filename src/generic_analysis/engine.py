"""Thin opt-in orchestration; never loads, cleans, persists or advances pipeline state."""

from copy import deepcopy

import pandas as pd

from .models import AnalysisResult
from .roles import infer_roles
from .router import route
from .statistics import compare_groups, describe_measure, detect_correlations


def analyze(data: pd.DataFrame, metadata: dict | None = None, *,
            group_pairs: tuple[tuple[str, str], ...] = ()) -> AnalysisResult:
    """Analyze a caller-approved snapshot; group comparisons require explicit pairs.

    Metadata uses {"columns": {name: {"role": ...}}, ...context...}.
    Identifier/ignore columns never enter statistics. No raw rows are retained.
    """
    roles = infer_roles(data, metadata)
    result = AnalysisResult(len(data), roles, deepcopy(metadata or {}))
    measures = [c for c, role in roles.items() if role == "measure"]
    if metadata is None:
        result.warnings.append("Roles are tentative dtype guesses; confirm identifiers, units and grain.")
    if data.empty:
        result.warnings.append("Dataset has no rows.")
    for name, role in roles.items():
        if role in {"identifier", "ignore"}:
            continue
        if data[name].isna().any():
            result.warnings.append(f"Missing observations in {name}; review upstream quality evidence.")
        if role == "measure":
            result.descriptive[name], result.distributions[name] = describe_measure(data[name])
            if result.descriptive[name]["non_finite"]:
                result.warnings.append(f"Non-finite observations in {name} excluded from calculations.")
        elif role == "category":
            result.descriptive[name] = {"count": int(data[name].count()),
                                        "missing": int(data[name].isna().sum()),
                                        "frequencies": data[name].value_counts(dropna=True).to_dict()}
        elif role == "time":
            times = data[name].dropna()
            result.time_hooks.append({"column": name, "count": len(times),
                                      "distinct_times": times.nunique(),
                                      "start": times.min() if len(times) else None,
                                      "end": times.max() if len(times) else None,
                                      "monotonic": times.is_monotonic_increasing,
                                      "duplicate_times": int(times.duplicated().sum())})
    result.correlations = detect_correlations(data, measures)
    for category, measure in group_pairs:
        if roles.get(category) != "category" or roles.get(measure) != "measure":
            raise ValueError("Group pairs require a category followed by a measure.")
        result.groups.append(compare_groups(data, category, measure))
    result.next_steps = route(result)
    return result
