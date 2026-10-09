"""WIP, domain-neutral exploratory analysis of approved pandas snapshots."""

from .engine import analyze
from .models import AnalysisResult, NextStep
from .roles import infer_roles
from .router import route

__all__ = ["analyze", "AnalysisResult", "NextStep", "infer_roles", "route"]
