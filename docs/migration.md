# Migration Notes: Version 0.3.0

The public project is now named `governed-data-pipeline` and its primary import namespace is `governed_data_pipeline`. It provides reusable engineering components with neutral synthetic examples. No wider-project notebooks, generated foundation tables or domain-specific rules are runtime dependencies.

## Imports and retained interfaces

Use new imports for new work:

```python
from governed_data_pipeline.cleaning import CleaningEngine
from governed_data_pipeline.profiling import profile_data
from governed_data_pipeline.validation import validate_fields
from governed_data_pipeline.pipeline import GovernedPipeline, PipelineConfig
```

The former `credit_risk_pipeline` namespace remains thin compatibility wrappers around the primary implementation. Existing profiler functions, flat DQ helpers, score gates, file-reader contracts and pipeline planning helpers remain available. The primary cleaner requires an explicit schema. A deprecated cleaner subclass supplies the previous applicant-ID default when older callers omit it, then delegates to the same implementation.

```powershell
python -m governed_data_pipeline --scenario clean
python -m governed_data_pipeline.database_demo --action bootstrap
```

Reinstall the local project after updating so package metadata and entry points match the checkout: `python -m pip install -e .`.

## Behavior changes

- Late CSV journal finalization failures preserve the original completed run and retry reporting separately. `RunFinalizationError.completed_run` supplies the result if reporting remains unavailable.
- Optional comparison columns behave as missing when absent. Required columns still fail structurally.
- Numeric band configuration rejects nonfinite/boolean/reversed bounds, blank labels and overlapping ranges.
- Durable quality reports retain descriptive before/after evidence and distinguish reported failures from unassessed source accuracy.
- New database extraction and CDC modules add explicit snapshot and change-processing interfaces. The CSV loader retains insert/reuse/conflict behavior; database updates and deletes use the separate database workflow.

## State and migration boundaries

Existing demonstration inputs are preserved. The primary generic CSV demo uses `customer_id`, `active` and `order_date`, with fresh folders beneath `data/local/governed_demo_v3/`. The deprecated `credit_risk_pipeline.demo` retains its previous fields and folders for compatibility. Use new reviewed job/state locations for changed source layouts or target constraints. The loader does not silently alter constraints, and capture verification rejects schema or trigger drift.

SQLite database progress belongs to the target transaction. CSV JSON progress remains separate. Do not interchange those checkpoints or infer that an append-only CSV loader can replay updates/deletes. See [reconciliation](reconciliation.md#replay-behavior) and [database/CDC](database_cdc.md).
