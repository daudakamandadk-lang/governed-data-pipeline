# Roadmap

## Implemented foundation

- Independent file extraction, profiling, typed validation, cleaning, record gates, transformation and loading.
- Connected CSV-to-SQLite orchestration with before/after quality evidence, durable quarantine, reconciliation and deferred JSON progress.
- Read-only SQLite snapshots and append-only composite cursor extraction.
- Explicit SQLite trigger capture for inserts, updates and deletes.
- Related-table snapshot bootstrap and strict change consumption, with successful target changes, evidence, event ledger and checkpoint committed together.
- Replay, drift and failure-boundary verification using temporary synthetic inputs.

This is a generic data-engineering project. Domain-specific generators, risk estimates, decisions, features and ML are outside its scope.

## Next engineering work

1. Study and reproduce the implemented failure cases and engine interfaces.
2. Design reviewed quarantine release and historical reprocessing.
3. Establish schema migration procedures and stronger historical target audits.
4. Introduce bounded extraction, transaction-aware event batching and retention policies before handling large datasets.
5. Add database/API adapters where concrete source requirements justify them.
6. Address concurrent writers, scheduling, operations and deployment after Python behavior is stable.

PostgreSQL logical replication/WAL CDC, API extraction, remote databases, production scheduling and streaming are planned. The present CDC implementation is local SQLite trigger capture with retained history and whole-state checks.

See [architecture](architecture.md), [database/CDC](database_cdc.md) and [operating boundaries](../README.md#operating-boundaries).
