# Reconciliation and Recovery

Reconciliation accounts for the selected input and checks that the accepted batch is stored as expected. Progress advances only after the configured evidence passes.

## Record accounting

```text
extracted records = pass + corrected + quarantine + reject
eligible records  = pass + corrected
eligible loaded batch = inserted + reused
target rows after load = target rows before load + inserted
```

“Eligible” and “inserted” differ. A stopped gate can identify three eligible rows and insert none.

The band transformation adds a derived column on a copy without changing grain. This implementation does not claim reconciliation for aggregation or future transformations that change row count or identity.

## Checks before progress commitment

1. Accepted batch size matches inserted plus reused rows.
2. Target growth matches newly inserted rows.
3. Every accepted primary key exists in the target.
4. Stored values match complete expected rows in current batch order, aligned by primary key.
5. Configured numeric totals match accepted values stored.
6. Dispositions account for every extracted row.
7. Persisted quarantine payloads/reasons match expected observations.
8. Source and reference files retain their observed fingerprints.

Checks cover the current accepted batch and target growth. They do not revalidate all historical rows or every related table. SQLite `REAL` is binary floating-point storage; total comparison does not make it exact currency.

Failed reconciliation withholds progress. A target load may already have committed, so withholding progress does not undo previous successful target transactions.

## Replay behavior

The loader uses one SQLite transaction:

| Existing key | Action |
| --- | --- |
| Absent | Insert new row |
| Present with identical stored values | Reuse existing row |
| Present with changed values | Raise replay conflict; roll back current load |

A conflict rolls back new rows inserted earlier in the same attempt. Earlier successful transactions remain. Declared unique fields are enforced against the current batch and existing target.

The loader does not silently update historical records. Existing-key mismatches require investigation; they are not transient retries.

An existing target must also have matching column types, the declared primary key and exactly the declared whole-column unique constraints. Adding or removing `unique` rules does not migrate the target. Missing or extra unique constraints, partial indexes and nonbinary collations fail target verification before loading.

For an intentional contract change, retain the original target, progress and audit evidence. Use a reviewed database migration, or rebuild from retained inputs into a separate compatible target with a distinct job and progress location. Check the rebuilt results before adopting them. Deleting progress or retrying an incompatible target does not resolve the schema mismatch.

## Audit evidence

Runs retain configuration, timestamps, status, stage events and failures. Quarantine observations retain positional identity, disposition, reasons and original/cleaned rows. Corrections retain original/cleaned cells and normalization reasons.

Repeating the same source-batch observation under the same policy avoids another identical quarantine entry. Changed content or policy creates a distinct observation. Counts describe historical observations, not a deduplicated current register.

Strict policy retains bad-row evidence while holding good rows back. Structural failure can retain every available row as quarantine evidence. An empty invalid file has no rows to store; its failure remains in events.

## Failure and retry boundaries

Selected transient I/O and SQLite busy/locked failures can retry within the configured limit. Invalid configuration, missing required files, rule failures, replay conflicts and reconciliation failures need corrective action.

An unchanged replay can recover from an unsuccessful progress write:

```text
attempt 1: insert six -> reconcile -> JSON progress write fails
attempt 2: select same six -> reuse six -> reconcile -> commit progress
target: six rows
```

Returned inserted/reused counts describe the final successful attempt. Events retain earlier attempts.

SQLite and JSON progress are separate stores. No transaction spans load, audit, reconciliation and progress. A crash after target commit can leave uncommitted progress; a failure after progress commit can leave incomplete final status. Retain the original source, database and journal for investigation. The workflow does not promise exactly-once processing across every crash.

Use one writer. Job/progress bindings within one database do not coordinate concurrent processes or separate databases.

## Quarantine after commitment

Permissive policy can commit past bad IDs only after durable quarantine evidence passes. The extractor subsequently uses strict `>` comparison against progress, so repairing an old row does not select it again.

Automatic release, older-row updates and historical reprocessing are future work. Changing or deleting progress without considering existing target rows and evidence is not a recovery procedure.

See [architecture](architecture.md) and [quality gates](data_quality_gates.md).
