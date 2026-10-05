# Data Quality Gates

The original score gate summarizes passed field checks. The connected workflow uses a separate record gate after cleaning and revalidation to control target loading.

## Compatible score gate

```python
from credit_risk_pipeline.gates import evaluate_gate

decision = evaluate_gate(score=0.94, pass_threshold=0.95, warn_threshold=0.90)
print(decision.status.value)  # WARN
```

Outcomes are `PASS`, `WARN` and `STOP`. Thresholds satisfy `0 <= warn_threshold <= pass_threshold <= 1`.

`dimension_score()` measures the share of field checks passed in one dimension. It does not measure valid rows. Empty check sets score `1.0`; that alone does not establish that an empty input is acceptable. Completeness owns missingness; validity and uniqueness assess present values.

The [score demo](../examples/dq_gate_demo.py) returns `0.667` because one of three field validity checks fails. It performs no persistence or record routing.

`can_continue(decision, allow_warning=True)` preserves its original default. Callers can pass `allow_warning=False` when warnings must stop their own workflow. The governed record gate has separately configured thresholds.

## Record dispositions

Every extracted record receives one post-cleaning disposition:

| Disposition | Meaning | Eligible for loading |
| --- | --- | --- |
| `pass` | No unresolved defect or recorded correction | Yes |
| `corrected` | Deterministic correction succeeded; no unresolved defect remains | Yes |
| `quarantine` | Unresolved rule/value failures need investigation | No |
| `reject` | No usable primary key | No |

Correction history does not override defects: a corrected record can still be quarantined. Classification retains positional identity and reasons; it does not discard rows.

The incremental workflow fails invalid/missing watermarks at extraction. Standalone classification can describe unusable keys, but extraction failures cannot always supply a safely ordered batch to quarantine.

## Gate policy

Record outcomes are lowercase `pass`, `warn` and `stop`. Thresholds declare maximum reject/quarantine rates and an optional quarantine warning rate. The gate combines those rates with batch-level structural failures.

Default synthetic policy is strict: any bad record stops the batch. Eligible rows are held back, while quarantine and correction evidence is durably retained. A stopped batch does not load its accepted target or commit progress.

`--allow-quarantine` explicitly enables the built-in demo's permissive policy. The demo permits a quarantine rate up to 60% and warns when it is above zero; its maximum reject rate stays zero. Bad rows and their evidence are persisted before eligible rows are loaded. Quarantine evidence is verified during reconciliation before progress commitment. Bad rows remain ineligible.

This flag applies only to the built-in scenarios. With `--config`, set the desired thresholds in the JSON `gate` settings; scenario flags do not override that policy.

Structural failures stop the batch regardless of acceptable individual cells. Missing required fields, unavailable references or unusable structure cannot be resolved by an aggregate rate.

## Validation order

```text
profile -> validate original -> clean -> validate cleaned
        -> classify -> record gate -> durable evidence -> eligible load
```

Before-checks describe source values. Post-cleaning issues and unresolved cleaner issues drive dispositions. Cleaning can resolve parsing defects or create duplicates after trimming, so the second validation is required.

Standalone engines leave ordering and policy to their caller.

## Progress and quarantine

The fresh dirty scenario has three eligible and three quarantined rows. Strict policy inserts zero rows. The permissive run loads keys `1`, `2` and `6`, retains bad observations and commits progress to `6`.

Progress means the batch is accounted for under recorded policy. It does not mean all extracted rows were accepted. Quarantined older IDs need a separate correction/reprocessing process; automatic release is outside this build.

See [reconciliation](reconciliation.md) and [engine boundaries](engine_boundaries.md).
