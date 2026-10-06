"""Load approved multi-table states inside a caller-owned SQLite transaction.

Quality decisions, source capture and checkpoint persistence belong to callers.
The loader reconciles every declared table and never commits the transaction.
"""

from copy import deepcopy

from .loading import ReplayConflict, sql_value
from .values import digest, json_text
from .sqlite_source import validate_contracts, quoted, sql_type, read_tables


class SqliteChangeLoader:
    """Apply approved final table states inside a caller-owned transaction.

    changed_keys maps tables to their affected original/new keys; omitted means
    bootstrap inserts. Unaffected rows must already equal the final state.
    """

    def __init__(self, schemas):
        validate_contracts(schemas)
        self.schemas = deepcopy(schemas)
        for schema in self.schemas.values():
            for rules in schema["columns"].values():
                if "foreign_key" not in rules:
                    continue
                parent, key = rules["foreign_key"].split(".")
                parent_schema = self.schemas.get(parent)
                if parent_schema is None or key not in parent_schema["columns"]:
                    raise ValueError("Change loader reference contract is unavailable")
                if key != parent_schema["primary_key"] and not parent_schema["columns"][key].get("unique"):
                    raise ValueError("Change loader reference key must be declared unique")

    @staticmethod
    def _transaction(connection):
        if not connection.in_transaction or not connection.execute("PRAGMA foreign_keys").fetchone()[0]:
            raise ValueError("Change loading requires an active transaction with foreign keys enabled")

    def create_tables(self, connection):
        self._transaction(connection)
        for table, schema in self.schemas.items():
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                raise ValueError(f"Bootstrap requires fresh target tables: {table}")
            definitions = []
            for column, rules in schema["columns"].items():
                definition = f"{quoted(column)} {sql_type(rules['dtype'])}"
                if column == schema["primary_key"]:
                    definition += " PRIMARY KEY NOT NULL"
                elif rules.get("required"):
                    definition += " NOT NULL"
                if rules.get("unique") and column != schema["primary_key"]:
                    definition += " UNIQUE"
                if "foreign_key" in rules:
                    parent, key = rules["foreign_key"].split(".")
                    definition += f" REFERENCES {quoted(parent)}({quoted(key)}) DEFERRABLE INITIALLY DEFERRED"
                definitions.append(definition)
            connection.execute(f"CREATE TABLE {quoted(table)} ({','.join(definitions)})")

    def row_digest(self, table, row):
        return digest([sql_value(row[column], sql_type(rules["dtype"])) for column, rules in self.schemas[table]["columns"].items()])

    def table_digest(self, table, frame):
        key = self.schemas[table]["primary_key"]
        return digest(sorted((json_text(row[key]), self.row_digest(table, row)) for row in frame.to_dict("records")))

    def apply(self, connection, final_tables, changed_keys=None):
        self._transaction(connection)
        if set(final_tables) != set(self.schemas) or changed_keys is not None and set(changed_keys) != set(self.schemas):
            raise ValueError("Change loading requires every declared final table")
        tokens = {}
        if changed_keys is not None:
            # Remove all affected keys before inserts to evaluate UNIQUE rules
            # against the final state instead of transient update ordering.
            for table, keys in changed_keys.items():
                keys = list(keys.values()) if isinstance(keys, dict) else list(keys)
                tokens[table] = {json_text(value) for value in keys}
                schema = self.schemas[table]
                key = schema["primary_key"]
                for value in keys:
                    connection.execute(f"DELETE FROM {quoted(table)} WHERE {quoted(key)}=?",
                                       (sql_value(value, sql_type(schema['columns'][key]['dtype'])),))
        for table, data in final_tables.items():
            schema = self.schemas[table]
            columns = list(schema["columns"])
            rows = data.to_dict("records")
            if changed_keys is not None:
                rows = [row for row in rows if json_text(row[schema["primary_key"]]) in tokens[table]]
            statement = f"INSERT INTO {quoted(table)} ({','.join(quoted(column) for column in columns)}) VALUES ({','.join('?' for column in columns)})"
            for row in rows:
                connection.execute(statement, tuple(sql_value(row[column], sql_type(schema["columns"][column]["dtype"])) for column in columns))
        actual = read_tables(connection, self.schemas)
        if any(self.table_digest(table, final_tables[table]) != self.table_digest(table, actual[table]) for table in final_tables):
            raise ReplayConflict("Target final-state reconciliation failed")
        if any(connection.execute(f"PRAGMA foreign_key_check({quoted(table)})").fetchall() for table in self.schemas):
            raise ReplayConflict("Target relationship reconciliation failed")
