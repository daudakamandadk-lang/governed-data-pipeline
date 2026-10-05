# Migration Notes

The working CSV-to-SQLite learning workflow is packaged under the existing `credit_risk_pipeline` namespace. Installed imports resolve inside this repository. Notebook directories and another checkout are not runtime dependencies.

Introductory helpers remain available. The connected workflow adds record-level acceptance and persistence; the original field-score gate remains an independent interface.

## Retained interfaces

| Existing interface | Use after migration |
| --- | --- |
| `profiling.profile_data(df)` | Independent descriptive profile |
| `profile_categorical`, `profile_numeric`, `profile_date` | Direct field profiling |
| `dq.field(...)` | Construct an original flat field rule |
| `dq.run_dq_checks(df, schema)` | Field-level completeness, validity and uniqueness summaries |
| `dq.dimension_score(results)` | Share of field checks passed |
| `gates.GateStatus`, `GateDecision`, `evaluate_gate` | Configured uppercase score gate |
| `gates.can_continue(...)` | Caller-controlled score continuation |
| `extraction.SourceType`, `SourceConfig`, `ExtractionEngine` | File readers and metadata |
| `pipeline.stage_plan()`, `stop_required(...)` | Compatibility helpers alongside executable orchestration |

Package name remains `credit-risk-pipeline`; import remains `credit_risk_pipeline`. Field helpers now report missing columns and assess blanks/type failures without the earlier unconditional column lookup errors. The scoring unit remains passed fields, not accepted rows. `stage_plan()` now lists the implemented stages rather than the former architecture sketch.

The [DQ score example](../examples/dq_gate_demo.py) uses the retained APIs.

## New execution surface

`GovernedPipeline`, `PipelineConfig` and `PipelineRun` provide connected orchestration in `pipeline.py`. The module exposes:

```powershell
python -m credit_risk_pipeline --scenario clean
python -m credit_risk_pipeline --scenario dirty
python -m credit_risk_pipeline --scenario dirty --allow-quarantine
python -m credit_risk_pipeline --config configs/governed_demo.json
```

Run separately from the repository root. Custom configuration uses existing inputs; scenario commands create only absent synthetic files.

`--scenario` and `--allow-quarantine` apply only without `--config`. A configured job uses its JSON source and gate thresholds; the scenario flags are ignored.

The reusable cleaner is named `CleaningEngine`, replacing the learning script's `LearningCleaningEngine` name. New engines live in `cleaning.py`, `validation.py`, `record_gates.py`, `transformation.py`, `loading.py`, `incremental.py` and `audit.py`. Neutral types live in `contracts.py`, avoiding dependencies from cleaning/validation into orchestration.

## Schema and gate distinction

The original DQ schema is a flat column-to-rule mapping. The governed contract adds `columns`, a required `primary_key`, logical types and optional comparisons. [Data contracts](data_contracts.md) shows both.

The old score gate asks whether a supplied score meets thresholds. Its `PASS`/`WARN`/`STOP` outcomes remain unchanged.

The record gate determines whether a classified batch may proceed. It uses post-cleaning disposition rates and structural failures. `pass` and `corrected` rows are eligible; `quarantine` and `reject` rows remain excluded. [Quality gates](data_quality_gates.md) explains why a field score cannot route rows.

## Persistence changes

`IdempotentSqliteLoader` inserts absent keys, reuses identical rows and raises on changed existing values. This is append-only insert-once behavior, not general upsert.

Targets must match the declared primary key and exact unique constraints. The loader does not add missing constraints or relax existing ones. Contract changes need a reviewed migration or a separate rebuilt target/job/progress; see [recovery guidance](reconciliation.md#replay-behavior).

Audit evidence is persisted before permitted loading. Target/value reconciliation and observed file checks precede JSON progress commitment. SQLite and progress remain separate stores; [reconciliation](reconciliation.md) describes replay and crash boundaries.

Scenario inputs are preserved. Clean and dirty scenarios have separate state. Public/reference datasets and provenance remain independent of synthetic examples.

## Scope

The README records the learning lineage. This package finishes the existing profiling, cleaning, DQ, loading and orchestration workflow. Database extraction, CDC, historical updates, automatic quarantine release, risk modeling and lending decisions remain outside scope.
