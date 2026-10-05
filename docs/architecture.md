# Architecture

The package connects independent engines into a governed CSV-to-SQLite workflow. Engine APIs can also be called directly. The orchestrator owns stage order, policy, persistence and progress commitment.

## Execution sequence

```text
start run; persist configuration
  -> observe source fingerprint
  -> select CSV rows above committed watermark
  -> read configured references; observe their fingerprints
  -> profile input
  -> validate before cleaning
  -> clean a copy
  -> validate after cleaning
  -> classify records
  -> evaluate record gate
  -> persist quarantine observations and corrections
       stopped: finish stopped run; no target writes or progress commitment
       no new rows: finish empty run; retain existing progress
       proceeding:
         -> select pass/corrected rows
         -> transform
         -> load SQLite
         -> reconcile target and audit evidence
         -> verify observed files
         -> commit JSON progress
         -> finish successful run
```

Initial validation describes what arrived. Post-cleaning validation and unresolved cleaning issues determine eligibility. A successful correction can resolve an original defect; a correction can also create a duplicate, which is why validation runs again.

## Component responsibilities

| Module | Responsibility | Boundary |
| --- | --- | --- |
| `extraction.py` | Read configured files and return metadata | Does not decide business validity |
| `incremental.py` | Select new CSV rows and explicitly manage JSON progress | Does not load targets |
| `profiling.py` | Describe structure, missingness, frequencies and distributions | Does not clean, accept or persist rows |
| `cleaning.py` | Normalize declared fields and return corrections/issues | Preserves input; does not invent values or discard rows |
| `validation.py` | Assess types, field rules, structure, relationships and references | Reports defects without repairs |
| `record_gates.py` | Classify records and evaluate batch thresholds | Does not write accepted or quarantined data |
| `transformation.py` | Derive configured bands on a copy | Does not grant eligibility or commit progress |
| `loading.py` | Insert/reuse accepted rows and reconcile stored evidence | Does not call the cleaner or apply gate policy |
| `audit.py` | Persist run events, quarantine observations and corrections | Does not select rows for loading |
| `pipeline.py` | Coordinate stages and failure boundaries | Owns the connected workflow |
| `contracts.py`, `values.py` | Share neutral types and value helpers | Contain no orchestration policy |

Compatible score helpers in `dq.py` and `gates.py` remain independently useful. They are distinct from the record gate used by the connected workflow.

## Persistence

One SQLite database holds the accepted target and audit tables:

| Table | Evidence |
| --- | --- |
| `etl_jobs` | Job identity and source/target/progress binding |
| `etl_runs` | Run identity, timestamps, configuration, status and summary |
| `etl_events` | Stage events, attempts and stage evidence |
| `etl_quarantine` | Observed bad rows, disposition, reasons, original and cleaned values |
| `etl_corrections` | Original/cleaned cell values and correction reasons |

Targets cannot use the reserved `etl_` prefix. Quarantine identity describes an observation of a source batch under a policy. It is not a deduplicated current register of business records.

JSON stores extraction progress separately. The order is: durable quarantine/corrections, load, reconciliation, then progress. Identical replay can reuse target rows when an earlier load committed but progress did not.

## Configuration and integrity

Configuration declares schema, gate thresholds, date formats, optional band transformation, reference paths, numeric totals and retry limit. Source/reference fingerprints detect changes during an observed run before progress is committed. They do not implement a general history of source updates.

Each job needs its own progress location. Journal bindings detect conflicting identities within the same database. They do not coordinate different databases or concurrent processes. Use one writer.

## Limits and downstream use

The incremental engine rereads a small append-only CSV and selects unique increasing integer watermarks. CDC, deletes, older-row updates, late arrivals and quarantine release are outside this build.

SQLite transactions protect individual target loads. SQLite and JSON have no shared transaction. Reconciliation covers the current accepted batch and target growth; full historical and cross-table reconciliation are future work.

Curated output can feed later analytics and feature engineering. PD, LGD, EAD, expected loss, machine learning and lending policy remain outside this package.

See [engine boundaries](engine_boundaries.md), [data contracts](data_contracts.md) and [reconciliation](reconciliation.md).
