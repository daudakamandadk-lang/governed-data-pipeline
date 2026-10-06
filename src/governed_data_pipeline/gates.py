"""Original score gate; the connected workflow uses record_gates instead."""
from dataclasses import dataclass
from enum import Enum
import math
import numbers


class GateStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    STOP = "STOP"


@dataclass(frozen=True)
class GateDecision:
    score: float
    status: GateStatus
    pass_threshold: float
    warn_threshold: float


def evaluate_gate(score, pass_threshold, warn_threshold):
    """Convert a finite quality score into PASS, WARN or STOP."""
    if any(isinstance(value, bool) or not isinstance(value, numbers.Real)
           or not math.isfinite(float(value)) for value in (score, pass_threshold, warn_threshold)):
        raise ValueError("Scores and thresholds must be finite numbers, excluding booleans")
    if not 0 <= score <= 1:
        raise ValueError("score must be between 0 and 1")
    if not 0 <= warn_threshold <= pass_threshold <= 1:
        raise ValueError("require 0 <= warn_threshold <= pass_threshold <= 1")
    status = GateStatus.PASS if score >= pass_threshold else GateStatus.WARN if score >= warn_threshold else GateStatus.STOP
    return GateDecision(score, status, pass_threshold, warn_threshold)


def can_continue(decision, allow_warning=True):
    return decision.status != GateStatus.STOP and (allow_warning or decision.status != GateStatus.WARN)
