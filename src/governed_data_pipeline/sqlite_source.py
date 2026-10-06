"""Read-only extraction of declared tables from a local SQLite database."""

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3

import pandas as pd

from .values import digest, missing
from .validation import validate_schema, matches_type


def quoted(name):
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError(f"Invalid SQLite identifier: {name!r}")
    return '"' + name + '"'


def sql_type(dtype):
    return {"integer": "INTEGER", "boolean": "INTEGER", "float": "REAL"}.get(dtype, "TEXT")


def validate_contracts(schemas):
    if not isinstance(schemas, dict) or not schemas:
        raise ValueError("Selected tables require a nonempty schema mapping")
    for table, schema in schemas.items():
        quoted(table)
        if table.startswith(("_cdc_", "_etl_db_")):
            raise ValueError("Business tables cannot use capture/audit prefixes")
        validate_schema(schema)
        for column in schema["columns"]:
            quoted(column)


def source_layout(connection, schemas):
    """Check names, affinities and a single declared business primary key."""
    result = {}
    for table, schema in schemas.items():
        entry = connection.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
        if entry != ("table",):
            raise ValueError(f"Selected source table is unavailable: {table}")
        info = connection.execute(f"PRAGMA table_info({quoted(table)})").fetchall()
        actual = {item[1]: item[2].upper() for item in info}
        expected = {column: sql_type(rules["dtype"]) for column, rules in schema["columns"].items()}
        keys = [item[1] for item in sorted(info, key=lambda item: item[5]) if item[5]]
        if actual != expected or keys != [schema["primary_key"]]:
            raise ValueError(f"Source table schema/primary key differs from its contract: {table}")
        indexes = []
        for item in connection.execute(f"PRAGMA index_list({quoted(table)})"):
            name = item[1].replace('"', '""')
            indexes.append((item, connection.execute(f'PRAGMA index_xinfo("{name}")').fetchall()))
        result[table] = {"columns": info,
                         "sql": connection.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0],
                         "indexes": sorted(indexes),
                         "foreign_keys": connection.execute(f"PRAGMA foreign_key_list({quoted(table)})").fetchall()}
    return result


def logical_frame(rows, schema):
    """Decode SQLite boolean storage without guessing other numeric tokens."""
    columns = list(schema["columns"])
    result = pd.DataFrame(rows, columns=columns, dtype=object)
    for column, rules in schema["columns"].items():
        values = result[column].tolist()
        if rules["dtype"] == "boolean":
            values = [bool(value) if type(value) is int and value in (0, 1) else value for value in values]
            if all(missing(value) or type(value) is bool for value in values):
                result[column] = pd.array(values, dtype="boolean")
            else:
                result[column] = pd.Series(values, dtype=object)
        elif rules["dtype"] == "integer" and all(missing(value) or type(value) is int for value in values):
            result[column] = pd.array(values, dtype="Int64")
        elif rules["dtype"] == "float" and all(missing(value) or type(value) in (int, float) for value in values):
            result[column] = pd.array(values, dtype="Float64")
    return result


def read_tables(connection, schemas):
    result = {}
    for table, schema in schemas.items():
        columns = ",".join(quoted(column) for column in schema["columns"])
        rows = connection.execute(f"SELECT {columns} FROM {quoted(table)} ORDER BY {quoted(schema['primary_key'])}").fetchall()
        result[table] = logical_frame(rows, schema)
    return result


@dataclass
class SqliteSnapshot:
    tables: dict
    schema_digest: str


@dataclass
class CompositeCursorResult:
    data: pd.DataFrame
    previous_cursor: tuple | None
    candidate_cursor: tuple | None
    upper_bound: tuple | None


class ReadOnlySqliteExtractor:
    def __init__(self, source_path, schemas):
        self.source_path = Path(source_path).resolve()
        self.schemas = schemas
        validate_contracts(schemas)

    def connect(self):
        if not self.source_path.is_file():
            raise FileNotFoundError(f"SQLite source does not exist: {self.source_path}")
        return sqlite3.connect(self.source_path.as_uri() + "?mode=ro", uri=True, timeout=5)

    def extract(self):
        with closing(self.connect()) as connection:
            connection.execute("BEGIN")
            layout = source_layout(connection, self.schemas)
            tables = read_tables(connection, self.schemas)
            connection.commit()
        return SqliteSnapshot(tables, digest(layout))

    def extract_incremental(self, table, watermark_column, tie_breaker, after=None, upper_bound=None):
        """Read an append-only interval and leave progress commits to the caller.

        The unique tie-breaker avoids losing equal watermarks. Values use SQL
        storage ordering, not parsed timezone chronology. Updates/deletes and
        later rows at/below the saved cursor require CDC instead.
        Date/timestamp bounds require the exact source storage text, preferably
        a returned candidate_cursor. Native date/datetime bounds are rejected
        because SQLite adapters can change their textual ordering.
        """
        if table not in self.schemas:
            raise ValueError("Incremental table must be explicitly selected")
        schema = self.schemas[table]
        for column in (watermark_column, tie_breaker):
            if column not in schema["columns"] or not schema["columns"][column].get("required"):
                raise ValueError("Cursor columns must be required contract fields")
        if watermark_column == tie_breaker or (tie_breaker != schema["primary_key"] and not schema["columns"][tie_breaker].get("unique")):
            raise ValueError("Cursor requires a separate unique tie-breaker")
        def bound(cursor):
            if cursor is None:
                return None
            if not isinstance(cursor, (tuple, list)) or len(cursor) != 2:
                raise ValueError("Cursor values must match the two configured logical types")
            values = []
            for value, column in zip(cursor, (watermark_column, tie_breaker)):
                dtype = schema["columns"][column]["dtype"]
                if dtype in {"date", "timestamp"} and not isinstance(value, str):
                    raise ValueError("Date/timestamp cursor values require source storage text")
                if missing(value) or not matches_type(value, dtype):
                    raise ValueError("Cursor values must match the two configured logical types")
                # SQLite binds some NumPy scalars as blobs; explicit numeric
                # storage values retain the same ordering as source numbers.
                values.append(int(value) if dtype == "integer" else float(value) if dtype == "float" else value)
            return tuple(values)
        after, upper_bound = bound(after), bound(upper_bound)
        wm, tie = quoted(watermark_column), quoted(tie_breaker)
        with closing(self.connect()) as connection:
            connection.execute("BEGIN")
            source_layout(connection, self.schemas)
            raw_cursors = connection.execute(f"SELECT {wm},{tie} FROM {quoted(table)}").fetchall()
            if any(any(missing(value) or not matches_type(value, schema['columns'][column]['dtype'])
                       for value, column in zip(row, (watermark_column, tie_breaker))) for row in raw_cursors):
                raise ValueError("Source cursor contains missing or invalid values")
            if len({row[1] for row in raw_cursors}) != len(raw_cursors):
                raise ValueError("Source cursor tie-breaker is not unique")
            upper = tuple(upper_bound) if upper_bound is not None else connection.execute(
                f"SELECT {wm},{tie} FROM {quoted(table)} ORDER BY {wm} DESC,{tie} DESC LIMIT 1"
            ).fetchone()
            rows = []
            if upper is not None:
                columns = ",".join(quoted(column) for column in schema["columns"])
                interval = f"({wm},{tie})<= (?,?)"
                parameters = list(upper)
                if after is not None:
                    interval += f" AND ({wm},{tie})>(?,?)"
                    parameters.extend(after)
                rows = connection.execute(f"SELECT {columns} FROM {quoted(table)} WHERE {interval} ORDER BY {wm},{tie}", parameters).fetchall()
            connection.commit()
        frame = logical_frame(rows, schema)
        candidate = tuple(frame.iloc[-1][[watermark_column, tie_breaker]]) if len(frame) else tuple(after) if after is not None else None
        if candidate is not None:
            candidate = tuple(value.item() if hasattr(value, "item") else value for value in candidate)
        return CompositeCursorResult(frame, tuple(after) if after is not None else None, candidate, upper)
