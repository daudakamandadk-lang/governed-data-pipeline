# Independent Engines and Orchestration

Combining engines in a workflow is appropriate when each component keeps a clear responsibility. The orchestrator decides when to call them and when progress is safe to advance.

| Module | Independent responsibility |
| --- | --- |
| `extraction`, `chunked`, `incremental` | Read files; return data, metadata or candidate progress |
| `sqlite_source` | Read declared SQLite tables or an append-only cursor interval |
| `sqlite_cdc` | Explicitly install/verify source capture and read consistent captured history |
| `profiling` | Describe observed data without generators or example imports |
| `validation` | Judge configured field and relationship rules without repairing values |
| `cleaning` | Normalize a copy and retain corrections/unresolved issues |
| `quality_reports` | Summarize before/after profiles and reported validation failures |
| `record_gates` | Classify rows and evaluate whether a batch proceeds |
| `transformation` | Derive new fields under validated non-overlapping band rules |
| `loading` | Insert/reuse/conflict persistence and accepted-batch reconciliation |
| `sqlite_change_loader` | Apply/reconcile approved related-table state inside a caller-owned transaction, without committing or judging quality |
| `audit`, `values` | Persist CSV run evidence and convert/hash supported audit values |
| `pipeline` | Order CSV stages, retry selected failures and commit file progress |
| `database_pipeline` | Connect snapshots/changes, related-state checks and atomic target progress |
| `generic_analysis` (WIP) | Describe caller-approved snapshots and suggest analytical investigations; no pipeline state or domain decisions |

`contracts` contains shared result/issue types. Engines do not depend on the CLI or another project's notebook paths. The public package can be installed and imported independently.

CSV orchestration and database orchestration have different persistence boundaries. The CSV workflow selects eligible records and commits JSON after load/reconciliation. The database workflow uses a strict whole-bundle gate and commits successful target changes, evidence, event ledger and checkpoint together.

Configured ownership checks are generic relationships between selected tables. They do not embed a particular industry's policy. Source generation and domain-specific modelling remain external responsibilities.

The [independent example](../examples/independent_engines.py) demonstrates direct use. [Database/CDC](database_cdc.md) describes snapshot and cursor interfaces. The older `dq`/`gates` helpers remain summary/score interfaces, separate from record routing.
