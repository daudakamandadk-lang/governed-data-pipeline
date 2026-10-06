# Quality Gates and Routing

Profiling describes observed values. Validation compares them with configured rules. Cleaning records permitted normalization. Revalidation supplies unresolved failures to record classification.

| Disposition | Meaning | CSV eligibility |
| --- | --- | --- |
| `pass` | No reported row failures or corrections | Eligible |
| `corrected` | Permitted corrections, with no unresolved row failures | Eligible |
| `quarantine` | Invalid values or relationships requiring investigation | Excluded |
| `reject` | Missing primary key prevents safe record identity | Excluded |

Structural failures stop the entire batch, including empty inputs with missing required columns. CSV thresholds compare reject/quarantine rates with configured maxima. `warn_quarantine_rate` can produce a warning below the stopping threshold. Eligibility and insertion are separate: a stopped batch may contain eligible rows while loading none.

The default CSV policy is strict. `--allow-quarantine` explicitly permits the supplied demonstration's bad-record rate. Original and cleaned observations, reasons and corrections are stored before eligible rows can load. After progress advances, repairing an older CSV row does not automatically release it from quarantine.

## Database changes

The SQLite database workflow uses a strict gate for every selected table and its related final state. A bad change stops the batch; business tables and the consumed sequence remain unchanged. Evidence includes before/after profiles, reported field failures, corrections and original/cleaned rows. Fixing the source and running consumption again reassesses the pending events and resulting state. This is not an automatic quarantine-release service.

`quality_reports.table_evidence()` supplies before/after profiles and per-field contract counts. It labels source accuracy as `not_assessed`. A row may fail several rules; cell-issue counts cannot be read as a distinct-row count. An empty dataset or unassessed field does not prove source quality.

## Score gates remain separate

The retained `gates.evaluate_gate()` accepts a caller-supplied score and returns uppercase `PASS`, `WARN` or `STOP`. `dq.dimension_score()` scores passed field checks. The main workflows use `record_gates` to route records; a descriptive field score cannot determine which individual rows to load.
