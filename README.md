# Credit Risk Pipeline — Work in Progress

**Python · pandas · NumPy · ETL · Data Quality · Metadata · Credit Risk**

This repository is the **data-pipeline layer of a larger end-to-end credit-risk system** I am building. Its job is to take source data through controlled extraction, profiling, validation, data-quality gates, cleaning, transformation, reconciliation and classification so that downstream credit-risk analytics and statistical models receive trusted, explainable data.

> **Status:** active work in progress. The repository deliberately distinguishes implemented prototypes from planned components. It is not presented as production-ready software or as a real lending decision system.

## Where this pipeline fits

```text
source data / synthetic data / approved public data
                     |
                     v
               EXTRACTION
                     |
                     v
                PROFILING
                     |
                     v
                VALIDATION
     completeness | validity | uniqueness
                     |
                     v
              DATA QUALITY GATE
                /      |      \
             PASS     WARN     STOP
               |        |        |
               |        |     investigate /
               |        |     quarantine
               v        v
                  CLEANING
                     |
                     v
                REVALIDATION
                     |
                     v
              TRANSFORMATION
                     |
                     v
              RECONCILIATION
                     |
                     v
               CLASSIFICATION
      PASS / CORRECTED / QUARANTINE / REJECT
                     |
                     v
                   LOAD
                     |
                     v
             CURATED TRUSTED DATA
                     |
                     v
          FEATURE ENGINEERING LAYER
                     |
                     v
      STATISTICAL CREDIT-RISK ENGINE
        PD / LGD / EAD / Expected Loss
                     |
                     v
        scoring, stress analysis, policy
                     |
                     v
       machine-learning models later
```

The pipeline is therefore **not the final model**. It is the governed data foundation that the later statistical and machine-learning risk engines depend on.

## What is currently represented in this repository

- A typed **extraction engine prototype** for CSV, JSON, Excel and Parquet files.
- Generic **data profiling** for categorical, numeric and date fields.
- Metadata-driven **data-quality checks** for completeness, validity and uniqueness.
- A configurable **data-quality gate** that returns PASS, WARN or STOP from a quality score and thresholds.
- A governed **pipeline stage plan** showing extraction through loading.
- Documentation for quality gates, quarantine/reject handling and the wider credit-risk architecture.
- Security and privacy controls intended to keep the public portfolio free of employer/client data, credentials and private infrastructure details.

## Data-quality philosophy

The project treats data quality as part of the pipeline rather than as a report produced at the end.

A dataset should be:
1. profiled before assumptions are made;
2. checked against schema/rule metadata;
3. evaluated at a quality gate;
4. cleaned only where an allowed correction exists;
5. validated again after cleaning;
6. reconciled before and after transformation/loading;
7. quarantined or rejected when it does not meet controlled acceptance rules.

Current implemented dimensions are **completeness, validity and uniqueness**. Consistency, timeliness, referential integrity and additional business-rule validation are part of the planned hardening sequence.

## Repository structure

```text
src/credit_risk_pipeline/
    extraction.py       # source reading + extraction metadata
    profiling.py        # structural/statistical profiling
    dq.py               # completeness, validity, uniqueness checks
    gates.py            # PASS/WARN/STOP gate evaluation
    pipeline.py         # governed stage ordering / orchestration skeleton

docs/
    architecture.md
    data_quality_gates.md
    roadmap.md

scripts/
    privacy_check.py

SECURITY.md
PORTFOLIO_NOTICE.md
LICENSE
```

## Local setup

Use Python 3.10 or newer. From this repository's root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe examples/dq_gate_demo.py
```

In VS Code, select the Python interpreter at `.venv/Scripts/python.exe`.
The synthetic demo prints a validity score of 0.667 and a WARN decision.
It checks three fields; one fails validity. This is the fraction of field
checks passed, not the fraction of valid rows.

The editable installation makes the `src/` package importable. Installing
requirements alone does not install this package.

## Current implementation limits

`pipeline.py` returns a stage plan; it does not execute an end-to-end ETL job.
Cleaning, transformation, quarantine routing, reconciliation and loading are
planned. A gate decision does not implement these behaviours by itself.

DQ helpers expect schema columns to exist and values to have suitable types.
Empty rule sets score 1.0; this does not prove an empty dataset is acceptable.
Null, dtype and missing-column handling need further testing.

The newest standalone chunked/incremental extraction learning work lives in
[the end-to-end learning repository](https://github.com/daudakamandadk-lang/Credit-Risk-Model-end-to-end-/tree/main/notebooks/02_governed_etl).
Understand and harden that work before promoting it into this package.

## Example DQ gate

A gate is intentionally generic. Thresholds are **configuration decisions**, not hard-coded business truths.

```python
from credit_risk_pipeline.gates import evaluate_gate

decision=evaluate_gate(
    score=0.94,
    pass_threshold=0.95,
    warn_threshold=0.90
)

print(decision.status)
# WARN
```

This means the pipeline can continue only under an explicitly defined warning policy; a score below the warning threshold would return **STOP**.

## Design principles

- **Metadata-driven rules:** schemas and rules should be configurable rather than buried inside pipeline code.
- **Separation of concerns:** extraction, profiling, validation, cleaning and loading remain separate components.
- **No silent data loss:** failed records should carry reason codes and move to a controlled quarantine/reject path.
- **Reconciliation:** row counts, key integrity and processing totals should be provable across stages.
- **Lineage:** source, transformation and quality outcomes should be traceable.
- **Risk estimate != lending decision:** later PD/LGD/EAD estimates remain separate from lending-policy decisions.
- **Learning to engineering:** logic is prototyped, understood and tested before it is promoted into reusable modules.

## Tech stack

- Python
- pandas
- NumPy
- SQL planned for staging/curated layers
- Power BI/visual reporting planned for quality and analytical outputs
- Git/GitHub for version control and documentation

## Public reference data

Two UCI datasets are catalogued for pipeline testing and later benchmarking:

- **Default of Credit Card Clients** — the committed CSV is an empty placeholder; data has not been imported.
- **South German Credit** — a reference file is present; inspect its format before loading it.

Additional public/reference sources planned for calibration and scenario work include Bank of Uganda publications, Uganda National Panel Survey data, World Bank Global Findex, IMF macroeconomic indicators, HMDA and SBA lending data.

See [data/public/README.md](data/public/README.md) and [metadata/data_sources.yml](metadata/data_sources.yml) for provenance and usage notes.

These datasets are reference inputs; foreign or historical datasets are not treated as current Uganda ground truth.

## Safety and data policy

This public repository is an independent portfolio project.

- No employer, client, taxpayer or other confidential operational data should be included.
- No production credentials, private hostnames, connection strings or internal infrastructure details should be committed.
- Synthetic data and properly documented public sources are the intended data inputs.
- Raw third-party datasets are not required to be redistributed in this repository.

Run the publication check before sharing changes:

```bash
python scripts/privacy_check.py
```

See [SECURITY.md](SECURITY.md) and [PORTFOLIO_NOTICE.md](PORTFOLIO_NOTICE.md).

## Roadmap

The wider build progresses through four connected layers:

1. **Data foundation & scenarios** — canonical schemas, synthetic/reference data and scenario configuration.
2. **Governed ETL & data quality** — this repository's main focus.
3. **Statistical credit-risk engine** — features, PD/LGD/EAD, expected loss, risk grades and stress analysis.
4. **Machine learning & model operations** — model comparison, validation, explainability, monitoring and deployment after the governed data foundation is stable.

## Author

**Dauda Kamanda**

Background in quantitative economics, data analysis, data quality/data architecture and financial engineering studies.

This repository is intended to demonstrate how I think about **data reliability, analytics engineering and risk-model foundations**, not to claim a finished production credit system.
