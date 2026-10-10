# Reconciliation and Recovery

Reconciliation compares processed data with persisted state before progress advances. Counts alone can match while values are wrong.

## CSV checks

The governed CSV loader verifies inserted/reused counts, expected target growth, accepted keys, complete batch values and configured numeric totals. The orchestrator also checks row accounting, durable quarantine payloads and unchanged input/reference fingerprints.

Band derivation adds a new field on a copy. Invalid rules fail before job writes. Uncovered accepted values fail before loading. The validator judges business constraints; transformation does not make invalid input acceptable.

### Replay behavior

An absent key inserts; an identical existing row reuses; a changed existing value raises `ReplayConflict` and rolls back the current load transaction. Declared unique fields are enforced across batches. Target primary-key and unique constraints must match the contract; missing optional columns are normalized to null without changing the table layout.

SQLite target writes and JSON progress are separate commits. A failed progress write can leave loaded rows available for identical replay. This append-only loader is not a general update/delete loader.

After data stages complete, finalization retries only `journal.finish()`. If those attempts fail, `RunFinalizationError` contains `completed_run` and `attempts`. The journal may still display `running`; its error does not mean already committed progress or target writes were rolled back. Record that same completed summary rather than replaying data stages to reconstruct reporting.

## Database checks and atomic progress

The database workflow checks source/capture identity, schema layout, sequence continuity and previously consumed event fingerprints. Pending events are projected from the current target using before-images and keys. The projected related state must satisfy contracts and reconcile to the consistent source snapshot. Final target rows are compared by complete value digests; SQLite foreign-key checks confirm declared relationships.

Successful business changes, quality evidence, the consumed-event ledger and checkpoint commit in one target SQLite transaction. Failure before that commit rolls back all of them. A failure detected after commit is resolved by reading the durable run and checkpoint; a verified committed result is returned with `recovered_after_commit=True`.

Strict quality stops preserve business tables and progress while recording stopped-run evidence. Exceptions attempt a separate failure audit after rollback. Neither path silently releases quarantined records or modifies source data.

These checks support local single-writer workflows. They do not establish external source accuracy, exact-currency arithmetic, cross-system distributed transactions or protection against every coordinated tampering scenario.
