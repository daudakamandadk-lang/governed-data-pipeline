"""Transparent exploratory rules; thresholds are heuristics, not evidence of significance."""

from .models import AnalysisResult, NextStep


def route(result: AnalysisResult, *, skew_threshold: float = 1.0,
          correlation_threshold: float = 0.7) -> list[NextStep]:
    if skew_threshold <= 0 or not 0 < correlation_threshold <= 1:
        raise ValueError("Thresholds require skew > 0 and 0 < correlation <= 1.")
    steps = []
    if result.warnings:
        steps.append(NextStep("review_quality_and_context", (), "; ".join(result.warnings)))
    for column, check in result.distributions.items():
        skew = check["skew"]
        if skew is not None and abs(skew) >= skew_threshold:
            steps.append(NextStep("inspect_distribution", (column,),
                                  "Heavy skew heuristic: compare mean/median and inspect segmentation."))
    for finding in result.correlations:
        if abs(finding["coefficient"]) >= correlation_threshold:
            steps.append(NextStep("investigate_relationship", finding["columns"],
                                  "Strong numeric association heuristic; association does not establish causation."))
    for group in result.groups:
        if (group["summary"]["count"] > 0).sum() >= 2:
            steps.append(NextStep("inspect_group_comparison", group["columns"],
                                  "Compare group sizes, means and medians; no significance claim."))
    for hook in result.time_hooks:
        if hook["distinct_times"] >= 2:
            steps.append(NextStep("review_time_structure", (hook["column"],),
                                  "Confirm grain, ordering and frequency before trend/growth analysis."))
    return steps
