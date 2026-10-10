# Migration Notes: Version 0.3.0 and repository separation

The public project is now named `governed-data-pipeline` and its primary import namespace is `governed_data_pipeline`. It provides reusable engineering components with neutral synthetic examples. No wider-project notebooks, generated foundation tables or domain-specific rules are runtime dependencies.

## Imports and retired compatibility namespace (2026-10-10)

Use new imports for new work:

```python
from governed_data_pipeline.cleaning import CleaningEngine
from governed_data_pipeline.profiling import profile_data
from governed_data_pipeline.validation import validate_fields
from governed_data_pipeline.pipeline import GovernedPipeline, PipelineConfig
```

The former `credit_risk_pipeline` compatibility namespace has been removed. Update imports to `governed_data_pipeline`. Existing generic profiler functions, flat DQ helpers, score gates, file-reader contracts and pipeline planning helpers remain available in that package. Cleaning requires an explicit schema; implicit domain-specific defaults are retired. Domain lessons and source datasets belong to the consuming private project. This separation does not claim a new release.

```powershell
python -m governed_data_pipeline --scenario clean
python -m governed_data_pipeline.database_demo --action bootstrap
```

Reinstall the local project after updating so package metadata and entry points match the checkout: `python -m pip install -e .`.

## Explicit gate names

New callers should distinguish score decisions from record-routing decisions:

```python
from governed_data_pipeline import GateThresholds, evaluate_record_gate, evaluate_score_gate
```

`evaluate_score_gate(score, pass_threshold, warn_threshold)` is the same callable as the retained package-root `evaluate_gate` and `gates.evaluate_gate`. `evaluate_record_gate(dispositions, thresholds=None, *, batch_failures=())` is the same callable as `record_gates.evaluate_gate`. `GateThresholds` is now also available at the package root. Existing names, signatures, threshold policies and connected workflow behaviour remain unchanged. Use the explicit names in new code; no existing caller needs a signature change. See [quality gates and routing](data_quality_gates.md#explicit-gate-interfaces) for result types and boundary behaviour.

## Behavior changes

- Late CSV journal finalization failures preserve the original completed run and retry reporting separately. `RunFinalizationError.completed_run` supplies the result if reporting remains unavailable.
- Optional comparison columns behave as missing when absent. Required columns still fail structurally.
- Numeric band configuration rejects nonfinite/boolean/reversed bounds, blank labels and overlapping ranges.
- Durable quality reports retain descriptive before/after evidence and distinguish reported failures from unassessed source accuracy.
- New database extraction and CDC modules add explicit snapshot and change-processing interfaces. The CSV loader retains insert/reuse/conflict behavior; database updates and deletes use the separate database workflow.

## State and migration boundaries

The checkout contains no data directory, bundled reference data or domain source catalogue. Running the primary generic CSV demo explicitly generates neutral `customer_id`, `active` and `order_date` fixtures beneath ignored `data/local/governed_demo_v3/` folders. The database demonstration likewise generates neutral customers/orders fixtures only when run. Existing local generic demonstration inputs are preserved by those commands. Old domain demonstration fields and folders are no longer supported. Use new reviewed job/state locations for changed source layouts or target constraints; do not reuse old checkpoints for a different source contract. The loader does not silently alter constraints, and capture verification rejects schema or trigger drift.

SQLite database progress belongs to the target transaction. CSV JSON progress remains separate. Do not interchange those checkpoints or infer that an append-only CSV loader can replay updates/deletes. See [reconciliation](reconciliation.md#replay-behavior) and [database/CDC](database_cdc.md).
