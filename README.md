# Governed Data Pipeline

A modular Python data-engineering pipeline with working CSV and local SQLite workflows. Profiling, validation, cleaning, record routing, transformation and loading can run independently. Orchestration connects them with quality evidence, reconciliation and controlled progress advancement.

Version 0.3.0 adds read-only database extraction, composite cursors and explicit SQLite trigger-based change capture. This public project contains generic engineering components and neutral synthetic demonstrations. Domain-specific generation, analysis and modelling belong to separate projects. A pristine checkout contains no data directory or bundled datasets; built-in fixtures are generated locally only when a demonstration is explicitly run.

## Start with the CSV example

Use Python 3.11 or newer. From this repository's root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m governed_data_pipeline --scenario clean
```

Use an existing virtual environment when available. Core dependencies are pandas and NumPy; optional Excel/Parquet readers use `pip install -e ".[file-formats]"`.

The scenario command creates an input only when absent. Existing inputs are preserved. Each scenario owns a separate source, target database and JSON progress file beneath `data/local/governed_demo_v3/`. Version 0.3 uses neutral `customer_id`, `active` and `order_date` fields; its new folders avoid adopting the older demonstration's inputs or checkpoints.

| Supplied CSV scenario | Expected behavior |
| --- | --- |
| Clean, fresh state | Six records load and progress advances to 6 |
| Clean, unchanged repeat | `no_new_rows`, without additional inserts |
| Dirty, strict policy | Three eligible and three quarantined records; batch stops before loading |
| Dirty, explicitly permissive | Eligible keys 1, 2 and 6 load after durable quarantine |

```powershell
.\.venv\Scripts\python.exe -m governed_data_pipeline --scenario dirty
.\.venv\Scripts\python.exe -m governed_data_pipeline --scenario dirty --allow-quarantine
.\.venv\Scripts\python.exe -m governed_data_pipeline --config configs/governed_demo.json
```

A custom configuration requires existing inputs and resolves relative paths from the working directory. It controls the source and gate policy; scenario flags apply only to built-in examples. Advancing past quarantined CSV IDs does not automatically select repaired historical rows later.

## Run the database and CDC example

Run these actions separately from the repository root:

```powershell
.\.venv\Scripts\python.exe -m governed_data_pipeline.database_demo --action bootstrap
.\.venv\Scripts\python.exe -m governed_data_pipeline.database_demo --action mutate
.\.venv\Scripts\python.exe -m governed_data_pipeline.database_demo --action changes
.\.venv\Scripts\python.exe -m governed_data_pipeline.database_demo --action changes
```

The neutral customers/orders demonstration uses `data/local/database_demo/source.sqlite` and `target.sqlite`. Bootstrap installs capture explicitly in its own demonstration source and loads two customers and two orders. Mutate writes five events in one source transaction: one update, two inserts and two deletes. Consumption leaves two customers and two orders and advances the checkpoint to 5. It validates the complete related state, applies changes, reconciles values and relationships, and commits successful evidence, consumed events and the checkpoint in one target SQLite transaction. An unchanged repeat reports `no_changes`.

A custom database job uses `--config path/to/database_job.json` with existing source tables and declared contracts. Add `--install-capture` only when deliberately installing capture into that mutable custom source. The built-in demonstration installs capture only in its own fixture.

[Database and CDC](docs/database_cdc.md) explains the APIs, transaction boundaries and recovery behavior. This is local trigger capture; PostgreSQL logical replication, WAL readers, API ingestion and remote databases remain planned.

## Implemented components

| Component | Responsibility |
| --- | --- |
| Full/chunked/incremental file extraction | Read records; return metadata or candidate progress |
| Read-only SQLite extraction | Consistent declared-table snapshots and composite cursor intervals |
| Profiling and quality reports | Describe before/after data and reported contract failures |
| Validation and cleaning | Enforce configured types/rules; preserve originals and correction reasons |
| Record gates | Classify pass/corrected/quarantine/reject and decide whether a batch proceeds |
| Transformation | Derive non-overlapping numeric bands without overwriting source fields |
| CSV loading and reconciliation | Insert/reuse/conflict behavior with accepted-row, value and total checks |
| Database change orchestration | Snapshot bootstrap, ordered change application and related-state reconciliation |
| Audit and progress | Durable evidence, run IDs, configuration identity and replay checks |

The profiler measures observed data; it does not prove source accuracy. The database workflow applies a strict gate to the complete selected state. Invalid changes retain failure evidence while leaving business tables and the checkpoint unchanged. Automatic quarantine release is not implemented.

## Verification and reading

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
.\.venv\Scripts\python.exe -B scripts/privacy_check.py
```

Tests use temporary synthetic inputs and exercise success, replay, drift, invalid changes and failure boundaries. The configured publication scan is a focused repository check.

Repository separation checks on **2026-10-10 passed all 116 tests** using
Python 3.14.6, pandas 3.0.6 and NumPy 2.5.3. The privacy scan also passed after
removing the legacy credit namespace and bundled datasets.

Pre-sync checks on **2026-10-10 passed all 120 tests**, including four new public
gate-interface compatibility checks, using the same runtime. The privacy scan
also passed. These are local results; independent hosted CI remains future work.

Rerun these checks for your current checkout and environment after changing engines, contracts or configuration.

- [Architecture](docs/architecture.md) and [independent engines](docs/engine_boundaries.md).
- [Contracts](docs/data_contracts.md), [gates](docs/data_quality_gates.md) and [reconciliation](docs/reconciliation.md).
- [Database/CDC](docs/database_cdc.md), [migration](docs/migration.md) and [roadmap](docs/roadmap.md).
- [Independent usage](examples/independent_engines.py) and [legacy score-gate example](examples/dq_gate_demo.py).

The supported import namespace is `governed_data_pipeline`. The package runs independently of consuming projects, notebooks and datasets. See the migration notes for the retired namespace and explicit-schema requirement.

## Where to develop changes

Develop generic engines, public APIs, tests and documentation in this repository.
Temporary export/build snapshots in consuming projects are historical copies;
they are not development homes. Private learning lessons can have different
contracts, so assess shared fixes in each project and verify the affected
behaviour there.

An editable installation uses Python source from this checkout. Reinstall with
`python -m pip install -e .` when dependency metadata or entry points change;
rebuild/reinstall deliberately if a consuming environment uses a wheel.

## Operating boundaries

Both demonstrations are small local lessons with one pipeline writer. CSV extraction rereads the file and assumes increasing unique integer IDs. Database processing reads the selected snapshot and retained change history; it does not provide bounded-memory streaming or event-retention management. Source and target databases have distinct transactions; successful target changes, evidence and checkpoint share one transaction. SQLite REAL is floating-point storage.

The package is an educational portfolio implementation. Contract changes, source layout changes and target migrations require explicit review. Production deployment, concurrent-writer coordination and additional database adapters need further design and verification.

Code is covered by [LICENSE](LICENSE). Caller-owned input provenance and usage terms remain separate: see [source provenance](metadata/README.md), [SECURITY](SECURITY.md) and [portfolio notice](PORTFOLIO_NOTICE.md). This repository bundles no datasets. Generated demonstration inputs, databases and progress remain local and excluded from Git.
