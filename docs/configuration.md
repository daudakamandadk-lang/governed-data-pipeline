# Configuration

Custom jobs use existing local inputs and explicit contracts. They do not
generate sample sources. Keep configurations containing sensitive source
details, input files and generated state outside tracked public content.

## CSV jobs

Use [configs/governed_demo.json](../configs/governed_demo.json) as a reference,
then create a local configuration for your source. A minimal job is:

```json
{
  "job_name": "items",
  "source": "data/local/items/input.csv",
  "database_path": "data/local/items/target.sqlite",
  "watermark_path": "data/local/items/progress.json",
  "target_table": "items",
  "watermark_column": "item_id",
  "schema": {
    "primary_key": "item_id",
    "columns": {
      "item_id": {"dtype": "integer", "required": true},
      "amount": {"dtype": "float", "required": true, "min": 0}
    }
  },
  "sum_columns": ["amount"]
}
```

Provide an existing CSV with `item_id` and `amount`, then run:

```bash
python -m governed_data_pipeline --config path/to/items_job.json
```

`PipelineConfig.from_json()` resolves source, database, progress and reference
paths relative to the working directory, or its explicit `workspace` argument
in Python. Paths are not relative to the configuration file. Source, target and
progress paths must be distinct.

| Setting | Purpose |
| --- | --- |
| `schema` | Primary key, logical column types and validation rules |
| `date_formats` | Explicit formats by date/timestamp field |
| `gate` | Reject/quarantine stopping maxima and optional quarantine warning level |
| `reference_paths` | CSV reference tables keyed by table name |
| `sum_columns` | Numeric fields included in reconciliation totals |
| `transform` | Optional numeric band source, new derived column and range rules |
| `max_attempts` | Retry limit from 1 to 5; default 2 |

The default gate is strict. Custom jobs use their configured thresholds;
`--allow-quarantine` and `--scenario` configure only built-in demonstrations.
The watermark field must be a required, unique integer field. This workflow
assumes append-only arrival with increasing IDs. It rereads the source and
does not select updated historical rows below committed progress.

See [contracts](data_contracts.md) for allowed rules and
[quality gates](data_quality_gates.md) for record eligibility. A numeric band
cannot overwrite an existing schema field, overlap another band or leave an
accepted value uncovered in the connected workflow.

## Database jobs

The database CLI accepts the fields of `DatabaseJobConfig`. For an existing
SQLite source whose `items` table has `item_id INTEGER PRIMARY KEY` and
`name TEXT`, a minimal configuration is:

```json
{
  "job_name": "items",
  "source_path": "data/local/items/source.sqlite",
  "database_path": "data/local/items/target.sqlite",
  "schemas": {
    "items": {
      "primary_key": "item_id",
      "columns": {
        "item_id": {"dtype": "integer", "required": true},
        "name": {"dtype": "string", "required": true}
      }
    }
  }
}
```

Review the source and install capture deliberately before bootstrap:

```bash
python -m governed_data_pipeline.database_demo --action bootstrap --config path/to/items_db.json --install-capture
python -m governed_data_pipeline.database_demo --action changes --config path/to/items_db.json
```

Capture installation creates metadata, a journal and triggers in that source.
It does not create business tables or input data. Source and target paths must
differ and resolve from the working directory. Bootstrap requires fresh
business target tables; an existing bootstrap follows documented replay
checks rather than silently replacing the target.

`schemas` declares each selected table, its exact source columns and a single
primary key. `date_formats` is nested by table and field. `owner_rules` can
check configured relationships in addition to references. All selected state
passes a strict gate. See [database and CDC](database_cdc.md) for the Python APIs,
capture verification and transaction boundaries.

## Existing state

Treat a job's inputs, contracts, target and progress as a reviewed unit. Do not
reuse a checkpoint for a different source layout or interchange CSV JSON
progress with database event sequences. Schema/constraint changes need an
explicit migration or a fresh reviewed job. The package does not silently
alter constraints or adopt changed capture definitions.

Quality evidence includes original and cleaned observations. Protect those
local files according to the data they contain. See
[reconciliation and recovery](reconciliation.md), [migration](migration.md) and
[security](../SECURITY.md).
