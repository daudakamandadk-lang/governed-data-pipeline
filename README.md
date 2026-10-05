# Governed CSV-to-SQLite Pipeline

A reusable Python pipeline for profiling, cleaning, validating and loading small CSV datasets into SQLite. Independent engines support direct use; the orchestrator connects them with record-level quality gates, durable audit records, replay checks and deferred progress commitment.

This is an educational and professional portfolio project under active development. It provides a working data-engineering workflow for a wider credit-risk project. It does not implement credit-risk models or lending decisions.

## Run the synthetic example

Use Python 3.11 or newer. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m credit_risk_pipeline --scenario clean
```

The command creates a small synthetic input only when that scenario's source file is absent. Existing source files are preserved. Clean and dirty scenarios use separate folders under `data/local/governed_demo/`, each holding `transactions.csv`, `target.db` and, after successful commitment, `progress.json`.

Run the following commands separately:

```powershell
.\.venv\Scripts\python.exe -m credit_risk_pipeline --scenario clean
.\.venv\Scripts\python.exe -m credit_risk_pipeline --scenario dirty
.\.venv\Scripts\python.exe -m credit_risk_pipeline --scenario dirty --allow-quarantine
```

| Scenario with the supplied input | Expected result |
| --- | --- |
| Clean, fresh state | Six eligible records loaded; progress advances to `6` |
| Clean, unchanged repeat | `no_new_rows`; no additional target rows |
| Dirty, strict policy, fresh state | Three eligible and three quarantined records; batch stops, no target writes, no progress commitment |
| Dirty, explicitly permissive after the strict stop | Keys `1`, `2` and `6` loaded; bad records durably retained; progress advances to `6` |
| Dirty, permissive unchanged repeat | `no_new_rows`; quarantine history remains available |

“Eligible” describes a record's disposition. A stopped batch can contain eligible records while inserting zero rows.

The permissive example demonstrates a deliberate policy choice: skip bad records after storing their evidence and continue with eligible records. Once progress advances past those IDs, repairing old CSV rows does not select them again. Quarantine release and historical reprocessing require a separate procedure.

The core installation needs pandas and NumPy. If you use the optional Excel or Parquet file readers, install their dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[file-formats]"
```

## Run from configuration

```powershell
.\.venv\Scripts\python.exe -m credit_risk_pipeline --config configs/governed_demo.json
```

A custom configuration uses existing input files; it does not generate sample data. The supplied JSON points to `data/local/governed_demo/transactions.csv`; populate that input or adjust `source` to an existing CSV before running it. Run from the repository root so relative paths resolve consistently. See [the supplied configuration](configs/governed_demo.json) and [data contracts](docs/data_contracts.md) for schema, gate, transformation and reference settings.

`--scenario` and `--allow-quarantine` apply only to built-in scenarios. When `--config` is supplied, the JSON configuration controls the source and gate policy; those scenario flags are ignored.

## What the workflow does

```text
CSV + reference inputs
  -> fingerprint and extract rows above committed progress
  -> profile -> validate original values
  -> clean a copy -> validate cleaned values
  -> classify each record -> evaluate the batch gate
  -> persist quarantine and correction evidence
       STOP: retain evidence; leave target and progress unchanged
       PROCEED: transform eligible rows -> load SQLite
                -> reconcile -> commit JSON progress -> finish run
```

The implementation includes:

- Declared field types, required values, allowed categories, numeric bounds, uniqueness, configured relationships and reference checks.
- Deterministic cleaning with original values, successful corrections and unresolved issues retained.
- Post-cleaning record dispositions: `pass`, `corrected`, `quarantine` and `reject`.
- SQLite audit tables for jobs, runs, events, quarantine observations and corrections.
- Insert-once loading: identical existing keys are reused; changed existing values fail the current load transaction.
- Reconciliation of the accepted batch, target growth, keys, values, configured numeric totals, quarantine evidence and observed source/reference fingerprints.
- Bounded retries for selected transient failures, with progress committed after durable evidence and successful reconciliation.

The original field-score DQ helpers and `PASS`/`WARN`/`STOP` score gate remain available. The executable workflow uses the separate record gate to control which rows reach loading. [Quality gates](docs/data_quality_gates.md) explains the distinction.

## Use the engines independently

Each engine accepts its own inputs and returns its own result. Profiling does not start cleaning, cleaning does not write SQLite, and loading does not commit extraction progress.

```python
from credit_risk_pipeline.profiling import profile_data
from credit_risk_pipeline.cleaning import CleaningEngine
from credit_risk_pipeline.validation import validate_fields
from credit_risk_pipeline.loading import IdempotentSqliteLoader

profile = profile_data(df)
cleaned = CleaningEngine().clean(df, schema, date_formats)
validation = validate_fields(cleaned.data, schema, references)

# Select and approve eligible rows before calling the loader.
loaded = IdempotentSqliteLoader("target.db").load(accepted_df, "transactions", schema)
```

The snippet assumes caller-supplied frames and contract settings. Use [the independent-engine example](examples/independent_engines.py) for a runnable demonstration. See [engine boundaries](docs/engine_boundaries.md) for ownership of validation, decisions and side effects.

The existing score example also remains runnable:

```powershell
.\.venv\Scripts\python.exe examples/dq_gate_demo.py
```

Its `0.667` validity score is the fraction of field checks passed. It is not the fraction of valid rows, and the example does not load data.

## Package layout

```text
src/credit_risk_pipeline/
    extraction.py       file reading and extraction metadata
    incremental.py      CSV selection and standalone JSON progress
    profiling.py        independent descriptive profiling
    cleaning.py         schema-guided normalization
    validation.py       cell, structure, relationship and reference checks
    dq.py               compatible field-level DQ summaries
    gates.py            compatible score gate
    record_gates.py     record dispositions and batch acceptance
    transformation.py  band derivation and reconciliation contracts
    loading.py          replay-safe SQLite loading and reconciliation
    audit.py            durable run, quarantine and correction history
    contracts.py        shared result, correction and issue types
    values.py           common missing-value and serialization handling
    pipeline.py         connected orchestration and compatibility helpers
```

Imports use the installed `credit_risk_pipeline` package. There are no imports from another checkout or notebook-directory path modifications.

## Operating boundaries

The incremental workflow assumes an append-only CSV with unique, increasing integer watermark values and one writer. It rereads the entire CSV before selecting rows; it is intended for small files.

Missing or invalid watermarks fail extraction because safe ordering is unavailable. Old-ID updates, late arrivals, deletes, composite watermarks, database extraction and CDC are outside this implementation.

SQLite and JSON progress are separate stores. A load can commit before reconciliation or progress writing fails; an unchanged retry can reuse identical target rows. A failure after progress commitment can also leave the journal incomplete. There is no transaction spanning all stores and no claim of exactly-once processing across every crash.

Reconciliation covers the current accepted batch and its target growth. It does not revalidate the entire historical target or every related table. SQLite `REAL` remains floating-point storage; numeric-total checks do not make it an exact currency representation.

See [architecture](docs/architecture.md), [reconciliation and recovery](docs/reconciliation.md), and [the roadmap](docs/roadmap.md) for detailed boundaries.

## Verification and publication

The workflow refresh passed **62 tests** on Python 3.12.14 and Python 3.14.6.
The installed wheel was also exercised outside the repository: clean/repeat,
strict/permissive quarantine, custom configuration and the console entry point.
These are dated checks of this build, not a guarantee about future changes.

The second environment used pandas 3.0.6 and NumPy 2.5.3. Dependency ranges are
declared in `pyproject.toml`; [requirements-tested.txt](requirements-tested.txt)
records the first verification environment without claiming a universal lock.

Run the automated checks with the installed package in your active environment:

```powershell
python -m unittest discover -s tests
```

Verified environment: Python 3.12.14, pandas 3.0.1 and NumPy 2.3.5. Python 3.11 is the minimum supported version because SQLite conflict handling uses its exception error-code attributes.

Run the publication scan before sharing changes:

```powershell
.\.venv\Scripts\python.exe scripts/privacy_check.py
```

Review staged files and generated evidence as described in [SECURITY.md](SECURITY.md). The scan checks configured patterns; it cannot establish that every file is safe to publish.

## Data, licensing and context

The runnable scenarios use synthetic data. Public reference datasets have their own provenance and licensing notes in [data/public/README.md](data/public/README.md) and [metadata/data_sources.yml](metadata/data_sources.yml). The committed credit-card CSV is an empty placeholder; the South German Credit file uses a whitespace-delimited format. Neither is required for the quickstart.

[MIT](LICENSE) applies to project code. Third-party data remains subject to its own terms. See [the portfolio notice](PORTFOLIO_NOTICE.md).

The workflow was developed in the [credit-risk learning repository](https://github.com/daudakamandadk-lang/Credit-Risk-Model-end-to-end-/tree/main/notebooks/02_governed_etl) and promoted here as reusable package modules. [Migration notes](docs/migration.md) describe the retained API and executable workflow.

**Author:** Dauda Kamanda.
