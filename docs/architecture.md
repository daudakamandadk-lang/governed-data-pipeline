# Architecture

The package separates reusable engines from workflow decisions. A validator judges configured rules, a cleaner records normalization, and a loader persists permitted data. An orchestrator controls ordering and progress.

## CSV workflow

```text
fingerprint -> extract -> profile -> validate original -> clean a copy
  -> validate cleaned -> classify -> gate -> persist quality/audit evidence
  -> select eligible rows -> derive fields -> load -> reconcile
  -> commit JSON progress -> finalize run reporting
```

Strict gates stop before target loading. An explicit permissive policy can retain bad records durably and load eligible rows. Progress follows reconciliation and unchanged source/reference fingerprints. JSON progress and SQLite writes are separate commits; replay-safe loading handles identical rows without promising a distributed transaction.

Finalization retries only the terminal journal write. A late reporting failure cannot rerun extraction and replace a completed six-row result with a zero-row result. `RunFinalizationError.completed_run` retains the completed summary for reporting recovery.

## Database workflow

```text
explicit source capture installation
  -> consistent snapshot + captured sequence
  -> bootstrap fresh target
  -> later read ordered changes and current source state
  -> clean/validate selected related tables -> strict gate
  -> project changes from current target -> reconcile with source snapshot
  -> apply changes + successful evidence + event ledger + checkpoint
     in one target SQLite transaction
```

Source reads use a consistent SQLite transaction. Installed source triggers write change events in the source transaction. The consumer validates source identity, selected schemas, trigger definitions, journal continuity, consumed-event evidence and target layout before accepting changes.

Invalid state stops the database batch. Target business tables and its checkpoint remain unchanged; stopped-run evidence is recorded. Exceptions roll back the target transaction, then attempt separate failure recording. If the audit store itself is unavailable, the original exception remains visible.

The independent composite-cursor extractor supports append-only ordering. The CDC orchestrator uses event sequences to include updates and deletes. These are different progress models.

See [engine responsibilities](engine_boundaries.md), [contracts](data_contracts.md), [database mechanics](database_cdc.md) and [reconciliation](reconciliation.md).
