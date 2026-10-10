# Governed Data Pipeline

A modular Python pipeline for validating, cleaning and loading tabular data with
quality evidence, reconciliation and controlled progress. Use the engines
independently or run connected CSV-to-SQLite and local SQLite change-capture
workflows.

**Python 3.11+ · pandas / NumPy · CSV and SQLite · MIT licensed**

[![CI](https://github.com/daudakamandadk-lang/governed-data-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/daudakamandadk-lang/governed-data-pipeline/actions/workflows/ci.yml)

## What it does

| Capability | Behaviour |
| --- | --- |
| Extraction | Full-file, chunked and incremental file readers; read-only SQLite snapshots and composite cursors |
| Quality controls | Before/after profiles, explicit typed contracts, recorded cleaning and row-level routing |
| Governed CSV loading | Durable quarantine, insert/reuse/conflict handling and value reconciliation before JSON progress advances |
| SQLite change capture | Explicit insert/update/delete triggers, related-table checks and ordered event consumption |
| Run evidence | Run IDs, configuration identity, quality reports and replay checks |

```text
Extract -> Profile -> Validate -> Clean -> Revalidate -> Gate
  -> Transform -> Load -> Reconcile -> Advance progress
                     with quality and run evidence
```

This repository runs independently of notebooks, datasets and any consuming
application. It contains no bundled datasets. Demonstrations generate small
neutral synthetic inputs locally when explicitly run.

## Quick start

Clone the repository and install from its root. On macOS or Linux:

```bash
git clone https://github.com/daudakamandadk-lang/governed-data-pipeline.git
cd governed-data-pipeline
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m governed_data_pipeline --scenario clean
```

On Windows PowerShell:

```powershell
git clone https://github.com/daudakamandadk-lang/governed-data-pipeline.git
cd governed-data-pipeline
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m governed_data_pipeline --scenario clean
```

A fresh clean run loads six records and advances progress to 6. Repeat the
command to get `no_new_rows` without additional inserts. Source, target and
progress files are written beneath ignored `data/local/governed_demo_v3/`.
Existing inputs are preserved.

Commands below use `python` from your environment. Use `.venv/bin/python` or
`.\.venv\Scripts\python.exe` directly if the environment is not activated.
Optional Excel/Parquet readers can be installed with
`python -m pip install -e ".[file-formats]"`.

## Demonstrations

### CSV quality gates

```bash
python -m governed_data_pipeline --scenario dirty
python -m governed_data_pipeline --scenario dirty --allow-quarantine
```

The strict run identifies three eligible and three quarantined records, then
stops before loading. The explicitly permissive run retains quarantine evidence
and loads eligible keys 1, 2 and 6. Each scenario uses its own input and state.

### SQLite snapshots and changes

Run these commands in order:

```bash
python -m governed_data_pipeline.database_demo --action bootstrap
python -m governed_data_pipeline.database_demo --action mutate
python -m governed_data_pipeline.database_demo --action changes
python -m governed_data_pipeline.database_demo --action changes
```

Bootstrap loads two customers and two orders. Mutation records five events in
one source transaction: one update, two inserts and two deletes. Consumption
leaves two rows in each table and advances the checkpoint to 5. The final repeat
reports `no_changes`. Files stay beneath ignored `data/local/database_demo/`.

Successful target changes, quality evidence, consumed-event records and the
checkpoint commit in one target SQLite transaction. Capture is installed only
in the demonstration source. For custom sources, installation requires an
explicit `--install-capture` decision. See [database and CDC](docs/database_cdc.md).

## Use your own data

```bash
python -m governed_data_pipeline --config path/to/csv_job.json
python -m governed_data_pipeline.database_demo --action bootstrap --config path/to/database_job.json
```

Custom jobs require existing inputs and reviewed contracts; they generate no
sample source. Relative paths resolve from the working directory. The CSV
[example configuration](configs/governed_demo.json) shows schema, gate,
transformation and state settings. See [configuration](docs/configuration.md) for
setup and state boundaries.

Engines also support direct Python use:

```python
from governed_data_pipeline import CleaningEngine, profile_data, validate_fields

profile = profile_data(data)
cleaned = CleaningEngine().clean(data, schema)
validation = validate_fields(cleaned.data, schema)
```

Supply a pandas DataFrame and an explicit schema. Cleaning operates on a copy
and records corrections and unresolved issues. See the runnable
[independent engines example](examples/independent_engines.py),
[data contracts](docs/data_contracts.md) and [public interfaces](docs/engine_boundaries.md).
New gate callers should use `evaluate_score_gate` or `evaluate_record_gate` to
make their intent explicit.

## Verification

```bash
python -B -m unittest discover -s tests -p 'test_*.py' -v
python -B scripts/privacy_check.py
```

Tests use temporary synthetic inputs and cover replay, drift, invalid changes
and failure boundaries. CI runs the tests, publication scan and package build.
The scan checks configured patterns; it does not replace reviewing staged
changes. Recorded local results and tested environment details are in
[verification](docs/verification.md).

## Operating boundaries

The connected workflows use local files and one pipeline writer. CSV processing
rereads the source and assumes increasing unique integer IDs. Advancing past a
quarantined ID does not automatically select a repaired historical row.

Database consumption reads the selected snapshot and retained event history;
bounded event batching and retention management are not implemented. Source
and target transactions are separate. CSV target writes and JSON progress also
commit separately, with identical-row replay supporting recovery. SQLite REAL
uses floating-point storage.

Profiling reports observations and configured failures; it does not establish
source accuracy. Contract or target-layout changes require explicit review.
Remote adapters, concurrent writers, scheduling and production deployment need
additional design and verification. See [reconciliation and recovery](docs/reconciliation.md)
and the [roadmap](docs/roadmap.md).

## Documentation and contributing

- [Documentation index](docs/README.md): architecture, contracts, gates and workflow details.
- [Contributing](CONTRIBUTING.md): development setup and change verification.
- [Migration notes](docs/migration.md): imports, gate interfaces and existing state.
- [Security and privacy](SECURITY.md) and [source provenance](metadata/README.md): safe local data use.

Software terms are in [LICENSE](LICENSE) and the [project notice](PORTFOLIO_NOTICE.md).
Caller-owned input licences and permissions remain separate.
