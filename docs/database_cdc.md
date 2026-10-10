# Local SQLite Extraction and Change Capture

The database workflow provides consistent snapshot handoff and governed change consumption using local SQLite files. It works with declared related tables and one pipeline writer. Source and target paths must differ.

## Extraction interfaces

`ReadOnlySqliteExtractor(source_path, schemas).extract()` opens the existing source read-only and reads selected tables in one consistent transaction. It returns the tables and a schema fingerprint. Selected physical columns, storage declarations and the single primary key must match their contracts.

`extract_incremental(table, watermark_column, tie_breaker, after=None, upper_bound=None)` returns an append-only interval ordered by a composite pair. A unique tie-breaker avoids skipping rows that share a watermark. It returns previous/candidate cursor information without saving progress. Callers must commit that cursor only after downstream success.

The cursor follows SQLite storage ordering. Date/timestamp bounds must be exact source storage text, as returned in `candidate_cursor`; native Python date/datetime bounds are rejected to avoid SQLite adapter formatting changes. Use consistent sortable timestamp representations. Updates, deletes and later arrivals at or below a committed cursor require a change-processing design.

## Capture installation

`SqliteChangeCapture(source_path, schemas).install()` explicitly writes capture metadata, an event journal and insert/update/delete triggers into an existing source. It does not create business data. Installation requires a mutable source and permission to modify its capture metadata and triggers. Use a separate local source when the original export must remain immutable.

Triggers record ordered sequences, table/operation, old/new keys and old/new row images in the same source transaction as the business changes. Capture checks verify source identity, installed trigger definitions, schema fingerprints and journal continuity. Source rollback also rolls back its captured events.

This mechanism is SQLite trigger-based CDC. It does not read PostgreSQL logical replication or a database WAL. The journal retains its entire history; no pruning or event-retention service is implemented.

## Bootstrap and consumption

```python
from governed_data_pipeline.database_pipeline import DatabaseJobConfig, SqliteDatabasePipeline
from governed_data_pipeline.sqlite_cdc import SqliteChangeCapture

config = DatabaseJobConfig(source_path=source, database_path=target,
                           schemas=schemas, date_formats=date_formats,
                           job_name="customers_orders")
SqliteChangeCapture(config.source_path, config.schemas).install()
pipeline = SqliteDatabasePipeline(config)
first = pipeline.bootstrap()
later = pipeline.run_changes()
```

Supply actual paths and reviewed contracts. Bootstrap requires fresh business target tables and an installed capture source. Repeating an existing bootstrap revalidates target rows against committed evidence, contracts and consumed history before returning `already_bootstrapped`. A caught-up source must also reconcile. Pending source changes are left for `run_changes()`; repeating bootstrap does not consume them.

Change consumption reads pending events and a consistent current source snapshot. Before-images must match target state. The projected target and final source must agree after cleaning, configured references/ownership rules and strict gates. Key changes captured at the source are supported; primary-key normalization such as trimming is blocked because it would alter tracked identity.

Successful changes, quality evidence, consumed-event fingerprints and the checkpoint commit in one target transaction. Invalid state returns `stopped` with target business rows/checkpoint unchanged. Exceptions roll back and attempt separate failure recording. An error after a verified commit can return the durable result with `recovered_after_commit=True`.

## Demonstration and limits

```bash
python -m governed_data_pipeline.database_demo --action bootstrap
python -m governed_data_pipeline.database_demo --action mutate
python -m governed_data_pipeline.database_demo --action changes
python -m governed_data_pipeline.database_demo --action changes
```

The demo uses neutral customers/orders in `data/local/database_demo/`. A fresh bootstrap loads two rows in each table. Mutate produces one update, two inserts and two deletes; change consumption advances to sequence 5 and leaves two rows in each table. An unchanged repeat reports `no_changes`.

Custom jobs use `--config path/to/database_job.json`. Capture installation into a custom source requires `--install-capture`; the demonstration installs it only in its own fixture. Consumption reads all pending events and selected state. There is no automatic quarantine release, bounded event batching, remote adapter, production scheduler or concurrent-writer coordination. See [reconciliation](reconciliation.md) before changing state or contracts.
