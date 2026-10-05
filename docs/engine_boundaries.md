# Engine Boundaries

Each engine owns one task and can be used without constructing the full pipeline. The orchestrator supplies policy and execution order when components run together.

## Inputs, results and side effects

| Engine/API | Caller supplies | Result and side effects |
| --- | --- | --- |
| `profile_data(df)` | DataFrame | Descriptive profile; no cleaning or persistence |
| `CleaningEngine().clean(df, schema, date_formats)` | Frame and contract | Copy, corrections and issues; no routing or database writes |
| `validate_fields(df, schema, references)` | Frame, table contract and references | Cell issues and batch failures; no repairs |
| `dq.run_dq_checks(df, schema)` | Frame and flat field schema | DQ summaries; no loading policy |
| `gates.evaluate_gate(score, pass_threshold, warn_threshold)` | Score and thresholds | Compatible score decision; no persistence |
| Record classification and gate | Cleaned frame, corrections, issues and thresholds | Dispositions and batch decision; no deletion or loading |
| `BandTransformer` | Eligible frame and band rules | Copy with derived column; no persistence |
| `IdempotentSqliteLoader(db).load(df, table, schema)` | Explicit accepted frame and contract | SQLite insert/reuse; conflicts roll back current load |
| Incremental CSV engine | Source, watermark and progress location | New-row selection; commitment is explicit |
| `RunJournal` | Job/run identity, policy and evidence | Durable SQLite audit |
| `GovernedPipeline` | `PipelineConfig` | Coordinated audit, accepted load, reconciliation and progress |

Shared issue, correction and result types reside in `contracts.py`. Value helpers reside in `values.py`. Core profiling, cleaning and validation do not import the pipeline to operate.

## Direct use

With caller-supplied data/configuration:

```python
from credit_risk_pipeline.profiling import profile_data
from credit_risk_pipeline.cleaning import CleaningEngine
from credit_risk_pipeline.validation import validate_fields

profile = profile_data(df)
cleaned = CleaningEngine().clean(df, schema, date_formats)
validation = validate_fields(cleaned.data, schema, references)
```

Cleaning is not acceptance. Callers must inspect unresolved issues, classify records, assess structural failures and apply policy before selecting a loadable frame.

Loading is a separate action:

```python
from credit_risk_pipeline.loading import IdempotentSqliteLoader

loader = IdempotentSqliteLoader("target.db")
load_result = loader.load(accepted_df, "transactions", schema)
```

The loader enforces target shape, replay behavior and declared uniqueness. It does not perform complete DQ, choose thresholds, persist quarantine or commit CSV progress.

[examples/independent_engines.py](../examples/independent_engines.py) provides a runnable demonstration through package imports.

## Orchestrated use

```powershell
python -m credit_risk_pipeline --scenario clean
```

The orchestrator validates before/after cleaning, gates records, persists evidence, transforms/loads eligible rows, reconciles and commits progress. Stage events preserve attempts and failures.

Independent APIs do not automatically provide these connected guarantees. Custom callers own ordering and durability decisions.

## Progress ownership

Selecting new rows and committing progress are distinct. Extraction does not certify a batch as processed. The orchestrator commits after accounting, required evidence, accepted target reconciliation and observed file checks succeed.

Permissive policy can advance past durably quarantined rows. Older bad records then need a separate recovery process; automatic release is outside this build.

See [architecture](architecture.md), [quality gates](data_quality_gates.md), [reconciliation](reconciliation.md) and [migration](migration.md).
