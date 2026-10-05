# Roadmap

The current milestone is a reusable, executable CSV-to-SQLite workflow. It packages the learning implementation with independent engines, governed orchestration and explicit limits.

## Delivered workflow

- File extraction and independent profiling.
- Declared types, completeness, validity, uniqueness, conditional relationships and reference checks.
- Deterministic cleaning with correction history.
- Post-cleaning dispositions and configurable batch gates.
- Durable events, quarantine observations and corrections.
- Insert-once SQLite loading with identical replay and conflict rollback.
- Current-batch reconciliation of rows, keys, values, totals and observed files.
- Deferred JSON progress commitment and bounded retries.
- Synthetic scenarios and direct-engine examples.
- Compatibility for original field-score DQ and gate APIs.

The incremental case remains small append-only CSVs with unique increasing integer watermarks and one writer.

## Next hardening priorities

1. Define and test historical correction/reprocessing, quarantine release and effects on target values/progress.
2. Strengthen recovery around separate SQLite and JSON stores, including incomplete journal finalization.
3. Extend reconciliation where a justified use case requires historical or cross-table evidence.
4. Improve large-file resource use without weakening ordering, source integrity or audit guarantees.
5. Broaden examples and failure coverage as contracts and transformations grow.

These are future work. Database extraction, CDC, deletes, late arrivals, composite watermarks and concurrent execution are outside this milestone.

## Wider project context

Curated data can support later feature engineering, statistics and PD/LGD/EAD or machine-learning work in the wider credit-risk project. Those capabilities belong to their own components. This package does not estimate risk or make lending decisions.

Public/reference inputs retain provenance and usage limits. Foreign or historical datasets do not establish current Uganda credit behavior.

See [architecture](architecture.md), [migration](migration.md) and [public reference data](../data/public/README.md).
