# Quality Gates and Routing

Profiling describes observed values. Validation compares them with configured rules. Cleaning records permitted normalization. Revalidation supplies unresolved failures to record classification.

| Disposition | Meaning | CSV eligibility |
| --- | --- | --- |
| `pass` | No reported row failures or corrections | Eligible |
| `corrected` | Permitted corrections, with no unresolved row failures | Eligible |
| `quarantine` | Invalid values or relationships requiring investigation | Excluded |
| `reject` | Missing primary key prevents safe record identity | Excluded |

Structural failures stop the entire batch, including empty inputs with missing required columns. CSV thresholds compare reject/quarantine rates with configured maxima. `warn_quarantine_rate` can produce a warning below the stopping threshold. Eligibility and insertion are separate: a stopped batch may contain eligible rows while loading none.

The default CSV policy is strict. `--allow-quarantine` explicitly permits the supplied demonstration's bad-record rate. Original and cleaned observations, reasons and corrections are stored before eligible rows can load. After progress advances, repairing an older CSV row does not automatically release it from quarantine.

## Database changes

The SQLite database workflow uses a strict gate for every selected table and its related final state. A bad change stops the batch; business tables and the consumed sequence remain unchanged. Evidence includes before/after profiles, reported field failures, corrections and original/cleaned rows. Fixing the source and running consumption again reassesses the pending events and resulting state. This is not an automatic quarantine-release service.

`quality_reports.table_evidence()` supplies before/after profiles and per-field contract counts. It labels source accuracy as `not_assessed`. A row may fail several rules; cell-issue counts cannot be read as a distinct-row count. An empty dataset or unassessed field does not prove source quality.

## Explicit gate interfaces

Use the explicit names for new callers:

| Interface | Inputs | Result |
| --- | --- | --- |
| `evaluate_score_gate(score, pass_threshold, warn_threshold)` | A finite quality score and thresholds between 0 and 1 | `GateDecision` with uppercase `PASS`, `WARN` or `STOP` in `status` |
| `evaluate_record_gate(dispositions, thresholds=None, *, batch_failures=())` | Classified records, optional `GateThresholds` and structural failures | `GateResult` with lowercase `pass`, `warn` or `stop` in `outcome`, plus counts, rates and reasons |

Both functions and `GateThresholds` can be imported from the package root:

```python
from governed_data_pipeline import GateThresholds, evaluate_record_gate, evaluate_score_gate
```

The explicit names are aliases of the existing callables, so signatures and results remain unchanged. The retained package-root `evaluate_gate` and `gates.evaluate_gate` still mean the score gate. `record_gates.evaluate_gate` still means the record gate used by the connected workflows. Existing imports continue to work; there is no automatic conversion between a score and record dispositions.

`dq.dimension_score()` scores passed field checks. A score at or above its pass threshold passes; otherwise one at or above its warning threshold warns. Record reject/quarantine rates stop only when they exceed the configured maximum; a quarantine rate exceeding its warning level can warn when the batch has not stopped. A structural failure always stops the record gate, including an empty batch. A descriptive field score cannot determine which individual rows to load.
