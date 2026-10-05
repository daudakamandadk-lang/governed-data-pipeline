"""Insert-once SQLite loading and key/value/total reconciliation for learning.

An existing key with identical values is a replay; changed values are a conflict,
not an update. Updates and deletes require a later change-processing policy.
"""

from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import sqlite3

import pandas as pd

from .values import audit_value, digest, missing
from .transformation import ReconciliationCheck, ReconciliationReport, _validate_identifier
from .validation import validate_schema


class ReplayConflict(ValueError):
    pass


@dataclass(frozen=True)
class GovernedLoadResult:
    table: str
    rows_before: int
    rows_after: int
    inserted: int
    reused: int


def sql_value(value, sql_type):
    if missing(value):
        return None
    value = audit_value(value)
    if sql_type == "INTEGER":
        return int(value)
    if sql_type == "REAL":
        return float(value)
    if not isinstance(value, str):
        raise ValueError("A TEXT field must contain text")
    return value


class IdempotentSqliteLoader:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.database_path, timeout=5)

    def _types(self, data, schema):
        result = {}
        mapping = {"integer": "INTEGER", "boolean": "INTEGER", "float": "REAL"}
        columns = [*schema["columns"], *sorted(column for column in data.columns if column not in schema["columns"])]
        for column in columns:
            _validate_identifier(column, "column")
            if column in schema["columns"]:
                result[column] = mapping.get(schema["columns"][column]["dtype"], "TEXT")
            else:
                # Derived fields in this learning transformer are text bands.
                result[column] = "TEXT"
        return result

    @staticmethod
    def prepare_batch(data, schema):
        """Copy into schema order, filling only absent optional fields with nulls."""
        validate_schema(schema)
        if not data.columns.is_unique:
            raise ValueError("Target columns must be distinct")
        prepared = data.copy()
        for column, rules in schema["columns"].items():
            if column not in prepared.columns:
                if rules.get("required"):
                    raise ValueError(f"Required target column missing: {column}")
                prepared[column] = None
            elif rules.get("required") and prepared[column].map(missing).any():
                raise ValueError(f"Required target field contains missing values: {column}")
        key = schema["primary_key"]
        if prepared[key].duplicated().any():
            raise ValueError("Target batch requires present, unique primary keys")
        columns = [*schema["columns"], *sorted(column for column in prepared.columns if column not in schema["columns"])]
        return prepared.loc[:, columns]

    @staticmethod
    def _verify_target(connection, table, types, schema):
        info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        key = schema["primary_key"]
        primary_columns = [item[1] for item in sorted(info, key=lambda item: item[5]) if item[5]]
        if {item[1]: item[2] for item in info} != types or primary_columns != [key]:
            raise ValueError("Target schema or primary-key constraint differs from this batch")
        expected_unique = {(column,) for column, rules in schema["columns"].items()
                           if rules.get("unique") and column != key}
        actual_unique = set()
        for index in connection.execute(f'PRAGMA index_list("{table}")').fetchall():
            if not index[2] or index[3] == "pk":
                continue
            name = index[1].replace('"', '""')
            fields = [item for item in connection.execute(f'PRAGMA index_xinfo("{name}")') if item[5]]
            # Partial, expression or nonbinary indexes do not implement the
            # schema's whole-column, exact-value uniqueness contract.
            if index[4] or any(item[2] is None or item[4] != "BINARY" for item in fields):
                raise ValueError("Target unique constraints differ from this schema")
            columns = tuple(item[2] for item in fields)
            if columns != (key,):
                actual_unique.add(columns)
        if actual_unique != expected_unique:
            raise ValueError("Target unique constraints differ from this schema")

    @staticmethod
    def rows(data, types):
        return [tuple(sql_value(value, types[column]) for column, value in zip(types, row))
                for row in data.loc[:, list(types)].itertuples(index=False, name=None)]

    def load(self, data, table, schema):
        _validate_identifier(table, "table")
        if table.startswith("etl_"):
            raise ValueError("Target names cannot use the audit table prefix etl_")
        data = self.prepare_batch(data, schema)
        key = schema["primary_key"]
        types = self._types(data, schema)
        expected = self.rows(data, types)
        key_position = data.columns.get_loc(key)
        definitions = [f'"{column}" {kind}' + (" PRIMARY KEY NOT NULL" if column == key else
                       " UNIQUE" if schema["columns"].get(column, {}).get("unique") else "")
                       for column, kind in types.items()]
        columns = ",".join(f'"{column}"' for column in types)
        placeholders = ",".join("?" for _ in types)
        inserted = reused = 0
        with closing(self.connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({",".join(definitions)})')
                self._verify_target(connection, table, types, schema)
                before = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for row in expected:
                    old = connection.execute(
                        f'SELECT {columns} FROM "{table}" WHERE "{key}"=?', (row[key_position],)
                    ).fetchone()
                    if old is not None:
                        if old != row:
                            raise ReplayConflict(f"Changed values for existing key: {row[key_position]!r}")
                        reused += 1
                    else:
                        try:
                            connection.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', row)
                        except sqlite3.IntegrityError as error:
                            if error.sqlite_errorcode in {sqlite3.SQLITE_CONSTRAINT_UNIQUE, sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY}:
                                raise ReplayConflict(f"Declared unique value conflicts for key: {row[key_position]!r}") from error
                            raise
                        inserted += 1
                after = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        return GovernedLoadResult(table, before, after, inserted, reused)

    def reconcile(self, result, batch, schema, sum_columns=()):
        _validate_identifier(result.table, "table")
        batch = self.prepare_batch(batch, schema)
        key = schema["primary_key"]
        types = self._types(batch, schema)
        expected = self.rows(batch, types)
        key_position = batch.columns.get_loc(key)
        columns = ",".join(f'"{column}"' for column in types)
        actual = []
        with closing(self.connect()) as connection:
            self._verify_target(connection, result.table, types, schema)
            count = connection.execute(f'SELECT COUNT(*) FROM "{result.table}"').fetchone()[0]
            for row in expected:
                stored = connection.execute(
                    f'SELECT {columns} FROM "{result.table}" WHERE "{key}"=?', (row[key_position],)
                ).fetchone()
                if stored is not None:
                    actual.append(stored)
        checks = []

        def add(name, wanted, observed):
            checks.append(ReconciliationCheck(name, wanted, observed, wanted == observed))

        add("accepted_accounted_for", len(batch), result.inserted + result.reused)
        add("target_growth", result.rows_before + result.inserted, count)
        add("batch_keys_present", len(expected), len(actual))
        # The primary key is unique. Querying in batch order aligns each record.
        add("batch_values_digest", digest(expected), digest(actual))
        for column in sum_columns:
            if column not in types or types[column] not in {"INTEGER", "REAL"}:
                raise ValueError(f"Reconciliation total requires a numeric field: {column}")
            position = batch.columns.get_loc(column)
            total = lambda rows: sum((Decimal(str(row[position])) for row in rows if row[position] is not None), Decimal(0))
            add(f"total:{column}", str(total(expected)), str(total(actual)))
        return ReconciliationReport(checks)
