# Data Contracts

A governed contract declares a required primary key, a `columns` mapping and optional comparisons. Each column declares one logical type: `string`, `category`, `integer`, `float`, `boolean`, `date` or `timestamp`.

```python
schema = {
    "primary_key": "order_id",
    "columns": {
        "order_id": {"dtype": "integer", "required": True},
        "customer_id": {"dtype": "string", "required": True,
                        "foreign_key": "customers.customer_id"},
        "amount": {"dtype": "float", "required": True, "min": 0},
    },
}
```

Supported rules include `required`, `unique`, `allowed`, finite numeric `min`/`max`, explicit `boolean_tokens`, references and configured comparisons. Primary keys are unique even without a separate `unique` flag. Optional missing values do not become duplicate values.

Missing required columns are structural failures. Missing required cells are row issues. Absent optional fields have missing-value semantics: a comparison involving an absent optional operand or condition is skipped just as it is for a present null. Values are never invented to make the comparison run. Extra CSV fields require explicit `allow_extra_columns`.

Comparisons use `left`, one of `right` or literal `value`, an `operator` (`le`, `lt`, `ge`, `gt`, `eq`, `ne`) and a reason `code`. An optional `when` names a field and an `equals` value. References require selected parent data with unique reference keys; checking that a referenced row exists does not alone establish ownership. `DatabaseJobConfig.owner_rules` can enforce configured owner relationships.

The cleaner uses explicit date formats and boolean tokens. Failed conversion preserves the original value and reports an issue. Non-midnight timestamps are not silently truncated into dates; date fields need `allow_time_truncation=True` for that deliberate conversion.

Band rules require finite nonboolean bounds, `low < high` when both exist, and nonempty labels. Lower bounds are inclusive, upper bounds exclusive. Overlaps are rejected; gaps remain visible as missing derived labels and block the connected CSV workflow when accepted values are uncovered.

## SQLite contracts

Selected source tables require exact declared columns, supported SQLite storage declarations (`INTEGER`, `REAL`, `TEXT`) and one declared primary key. The database target enforces required fields, declared uniqueness and deferred references. Changing schemas or installed capture definitions requires explicit migration or a fresh reviewed job, rather than silent adaptation.

## Retained summary interface

`dq.field()` and `dq.run_dq_checks()` retain the older flat field-rule mapping. `dimension_score()` measures the share of field checks passed. It is not a row-acceptance score. The governed typed validator and record gates supply the stronger workflow contract; see [migration](migration.md).
