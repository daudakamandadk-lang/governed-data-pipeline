"""Small synthetic demonstration of DQ checks and a quality gate.

The thresholds below are illustrative choices for this exercise.
"""

import pandas as pd
from governed_data_pipeline.dq import field,run_dq_checks,dimension_score
from governed_data_pipeline.gates import evaluate_gate

data=pd.DataFrame({
    "order_id":["O001","O002","O003"],
    "total":[1200,-50,800],
    "product_type":["Hardware","Office","Hardware"]
})

schema={
    "order_id":field(required=True,unique=True),
    "total":field(required=True,min_value=0),
    "product_type":field(
        required=True,
        allowed=["Hardware","Office","Kitchen"]
    )
}

results=run_dq_checks(data,schema)
validity_score=dimension_score(results["validity"])

decision=evaluate_gate(
    score=validity_score,
    pass_threshold=1.00,
    warn_threshold=0.60
)

print("DQ results:",results)
print("Validity score:",round(validity_score,3))
print("Gate decision:",decision.status.value)
