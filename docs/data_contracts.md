# Data Contracts

The connected workflow uses a table schema to describe expected values before cleaning and acceptance. Configuration also supplies operational policy: source/output paths, progress field, gates, date formats, transformations and references.

See [configs/governed_demo.json](../configs/governed_demo.json) for the runnable contract.

## Table schema

A minimal schema declares a required primary key and column rules:

```json
{
  "table": "transactions",
  "primary_key": "transaction_id",
  "columns": {
    "transaction_id": {"dtype": "integer", "required": true, "unique": true},
    "applicant_id": {"dtype": "string", "required": true},
    "amount": {"dtype": "float", "required": true, "min": 0},
    "segment": {
      "dtype": "category",
      "required": false,
      "allowed": ["retail", "business"]
    }
  }
}
```

The incremental watermark is an increasing integer field. The primary key identifies target rows for insert-once loading. The demo uses the same field for both.

Rules apply to individual values. A mixed pandas column is assessed cell by cell; its container dtype does not prove every value is suitable.

## Supported logical types

| Type | Cleaned representation and checks |
| --- | --- |
| `string`, `category` | Text when present; trim whitespace; enforce allowed values |
| `integer` | Finite whole number; fractional values and booleans are invalid |
| `float` | Finite real number; configured numeric bounds |
| `boolean` | Native boolean or explicitly recognized text token |
| `date` | Canonical date following configured format-based cleaning |
| `timestamp` | Timestamp following configured format-based cleaning |

Numeric text can be normalized when parsing is valid. Nonfinite numbers remain defects. The cleaner never invents a missing amount, category or date.

Date and timestamp fields need input formats in `date_formats`. The demo's fixed policy reference date is configuration, not a live clock check.

A format may be a string or a list of accepted formats. If multiple configured formats parse one value into different dates, cleaning records an `ambiguous_date` issue rather than choosing an interpretation.

A `date` value with non-midnight time is blocked by default with `date_time_truncation_blocked`. Discarding that time requires an explicit field rule:

```json
{"dtype": "date", "required": true, "allow_time_truncation": true}
```

`allow_time_truncation` must be a boolean and is supported only on `date` fields. Use `timestamp` when time must be preserved. Configured input formats still apply; the flag does not permit an otherwise unparseable value.

Boolean text defaults to `true` and `false`, with surrounding whitespace and case normalized. Custom tokens are explicit:

```json
{"dtype": "boolean", "boolean_tokens": {"yes": true, "no": false}}
```

Keys use trimmed lowercase text and values use JSON booleans. Numeric `1`/`0` and unfamiliar text are not automatically inferred as booleans.

## Missingness, uniqueness and structure

Blank text becomes missing. Required missing cells fail completeness. Optional missing values do not fail uniqueness or range checks.

Missing required columns and unexpected columns are structural failures. `allow_extra_columns: true` explicitly permits additional fields. Missing optional columns are materialized as NULL for governed target loading.

Present values declared `unique` are checked within the batch. The governed loader also enforces them against the existing target, including optional unique fields. NULL remains allowed for optional fields. A conflict fails the load transaction rather than silently dropping or overwriting a row.

An existing target must match the declared column types, primary key and unique constraints. This loader does not perform schema migration. See [target compatibility and recovery](reconciliation.md#replay-behavior) before changing a contract for a previously loaded target.

Governed text extraction preserves identifiers such as `"001"` and literal `"NA"`. Invalid or missing incremental watermarks fail extraction before record quarantine because safe selection cannot proceed.

## Relationships and time rules

A comparison declares an operator, a left field and exactly one right field or literal value:

```json
{
  "left": "application_date",
  "operator": "le",
  "right": "snapshot_date",
  "code": "application_after_snapshot"
}
```

This requires `application_date <= snapshot_date`. Operators are `le`, `lt`, `ge`, `gt`, `eq` and `ne`. A `when` condition can restrict a rule:

```json
{
  "left": "employment_tenure",
  "operator": "eq",
  "value": 0,
  "when": {"column": "employed", "equals": false},
  "code": "unemployed_with_tenure"
}
```

Every referenced field must exist in the contract. Comparisons skip missing or already-invalid cells; completeness/type checks supply those reasons. Timezone disagreements are not silently aligned.

## Reference checks

A field may declare `foreign_key: "applicants.applicant_id"`. Configuration maps the reference table name to an existing CSV in `reference_paths`.

Unavailable tables/columns and duplicate reference keys stop the batch. Unknown present identifiers produce row-level reasons. Reference inputs are read only; their observed fingerprints are checked before progress commitment.

## Legacy field schemas

Compatible DQ helpers accept the earlier flat mapping:

```python
from credit_risk_pipeline.dq import field

schema = {
    "application_id": field(required=True, unique=True),
    "requested_amount": field(required=True, min_value=0),
}
```

This supports the field-score demo. It is distinct from the table schema passed to the governed cleaner, validator and loader. [Migration notes](migration.md) explains the retained interfaces.
