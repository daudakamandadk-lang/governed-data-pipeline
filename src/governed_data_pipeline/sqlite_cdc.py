"""Explicit local SQLite trigger capture, separate from extraction/loading.

This journal is not PostgreSQL logical or WAL CDC. Selected tables must keep
their declared schema and installed triggers. All available committed events
are read together; this small-database lesson deliberately has no event limit.
"""

from contextlib import closing
from dataclasses import dataclass, asdict
import json
import sqlite3
from uuid import uuid4

from .values import digest, json_text
from .sqlite_source import ReadOnlySqliteExtractor, quoted, source_layout, read_tables


@dataclass(frozen=True)
class ChangeEvent:
    sequence: int
    table: str
    operation: str
    old_key: object
    new_key: object
    old_row: dict | None
    new_row: dict | None

    @property
    def fingerprint(self):
        return digest(asdict(self))


@dataclass
class CapturedSnapshot:
    source_id: str
    high_water: int
    tables: dict
    events: list
    history: list


class SqliteChangeCapture(ReadOnlySqliteExtractor):
    def _triggers(self):
        result = {}
        for table, schema in self.schemas.items():
            key = quoted(schema["primary_key"])
            def image(alias):
                pairs = ",".join(f"'{column}',{alias}.{quoted(column)}" for column in schema["columns"])
                return f"json_object({pairs})"
            for operation in ("INSERT", "UPDATE", "DELETE"):
                name = f"_cdc_{table}_{operation.lower()}"
                old_key = f"json_quote(OLD.{key})" if operation != "INSERT" else "NULL"
                new_key = f"json_quote(NEW.{key})" if operation != "DELETE" else "NULL"
                old_row = image("OLD") if operation != "INSERT" else "NULL"
                new_row = image("NEW") if operation != "DELETE" else "NULL"
                result[name] = (
                    f"CREATE TRIGGER {quoted(name)} AFTER {operation} ON {quoted(table)} BEGIN "
                    "INSERT INTO _cdc_events(table_name,operation,old_key,new_key,old_row,new_row) "
                    f"VALUES('{table}','{operation}',{old_key},{new_key},{old_row},{new_row}); "
                    "UPDATE _cdc_meta SET last_sequence=last_insert_rowid() WHERE singleton=1; END"
                )
        return result

    def install(self):
        """Explicitly add capture to an existing local source; never seed data."""
        if not self.source_path.is_file():
            raise FileNotFoundError(f"SQLite source does not exist: {self.source_path}")
        with closing(sqlite3.connect(self.source_path, timeout=5)) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute("SELECT name FROM sqlite_master WHERE name GLOB '_cdc_*'").fetchall()
                if existing:
                    source_id, high_water = self._verify(connection)
                    return source_id
                layout = source_layout(connection, self.schemas)
                connection.execute("CREATE TABLE _cdc_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
                                   "source_id TEXT NOT NULL,version INTEGER NOT NULL,contract TEXT NOT NULL,"
                                   "physical_digest TEXT NOT NULL,last_sequence INTEGER NOT NULL)")
                connection.execute("CREATE TABLE _cdc_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
                                   "table_name TEXT NOT NULL,operation TEXT NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')),"
                                   "old_key TEXT,new_key TEXT,old_row TEXT,new_row TEXT)")
                source_id = uuid4().hex
                connection.execute("INSERT INTO _cdc_meta VALUES(1,?,1,?,?,0)",
                                   (source_id, json_text(self.schemas), digest(layout)))
                for statement in self._triggers().values():
                    connection.execute(statement)
            return source_id

    def _verify(self, connection):
        names = {item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"_cdc_meta", "_cdc_events"} <= names:
            raise ValueError("Capture metadata/journal missing; install capture explicitly")
        meta_columns = [item[1] for item in connection.execute("PRAGMA table_info(_cdc_meta)")]
        event_columns = [item[1] for item in connection.execute("PRAGMA table_info(_cdc_events)")]
        if meta_columns != ["singleton", "source_id", "version", "contract", "physical_digest", "last_sequence"] or event_columns != [
            "sequence", "table_name", "operation", "old_key", "new_key", "old_row", "new_row"
        ]:
            raise ValueError("Capture metadata/journal schema drift")
        event_info = connection.execute("PRAGMA table_info(_cdc_events)").fetchall()
        journal_sql = connection.execute("SELECT sql FROM sqlite_master WHERE name='_cdc_events'").fetchone()[0]
        if event_info[0][2].upper() != "INTEGER" or event_info[0][5] != 1 or "AUTOINCREMENT" not in journal_sql.upper():
            raise ValueError("Capture journal sequence constraint changed")
        rows = connection.execute("SELECT source_id,version,contract,physical_digest,last_sequence FROM _cdc_meta WHERE singleton=1").fetchall()
        if len(rows) != 1:
            raise ValueError("Capture identity is unavailable")
        source_id, version, contract, physical, high_water = rows[0]
        if not isinstance(source_id, str) or not source_id or version != 1 or contract != json_text(self.schemas):
            raise ValueError("Capture source identity/configuration differs")
        if digest(source_layout(connection, self.schemas)) != physical:
            raise ValueError("Captured source schema drift")
        normalize = lambda statement: " ".join(statement.split()).rstrip(";")
        for name, expected in self._triggers().items():
            row = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
            if row is None or normalize(row[0]) != normalize(expected):
                raise ValueError(f"Capture trigger missing or changed: {name}")
        sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='_cdc_events'").fetchone()
        actual_sequence = sequence[0] if sequence else 0
        if type(high_water) is not int or high_water < 0 or actual_sequence != high_water:
            raise ValueError("Capture sequence metadata differs from journal allocation")
        maximum = connection.execute("SELECT COALESCE(MAX(sequence),0) FROM _cdc_events").fetchone()[0]
        if maximum != high_water:
            raise ValueError("Capture journal tail missing; retention or corruption gap")
        return source_id, high_water

    def verify(self):
        with closing(self.connect()) as connection:
            connection.execute("BEGIN")
            return self._verify(connection)

    @staticmethod
    def _events(connection, high_water):
        result = []
        for sequence, table, operation, old_key, new_key, old_row, new_row in connection.execute(
            "SELECT * FROM _cdc_events WHERE sequence<=? ORDER BY sequence", (high_water,)
        ):
            parse = lambda value: json.loads(value) if value is not None else None
            result.append(ChangeEvent(sequence, table, operation, parse(old_key), parse(new_key), parse(old_row), parse(new_row)))
        return result

    def _read(self, previous_sequence=None, after_read=None):
        with closing(self.connect()) as connection:
            connection.execute("BEGIN")
            source_id, high_water = self._verify(connection)
            tables = read_tables(connection, self.schemas)
            if after_read:
                after_read()
            history = self._events(connection, high_water)
            events = [] if previous_sequence is None else [item for item in history if item.sequence > previous_sequence]
            if previous_sequence is not None:
                if type(previous_sequence) is not int or not 0 <= previous_sequence <= high_water:
                    raise ValueError("Checkpoint exceeds source sequence or is invalid")
                if [item.sequence for item in events] != list(range(previous_sequence + 1, high_water + 1)):
                    raise ValueError("Capture retention gap; required change events are missing")
            connection.commit()
        return CapturedSnapshot(source_id, high_water, tables, events, history)

    def snapshot(self, *, after_read=None):
        return self._read(after_read=after_read)

    def changes_after(self, sequence, *, after_read=None):
        return self._read(sequence, after_read)
