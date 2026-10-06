"""Strict local snapshot/trigger-CDC orchestration over independent engines.

Business changes, successful evidence and the consumed source sequence commit
in ONE target SQLite transaction. Source capture is explicitly installed by a
caller. This is a small local database lesson, not an external exactly-once or
PostgreSQL/WAL replication claim.
"""

from contextlib import closing
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .cleaning import CleaningEngine, CleaningIssue
from .loading import ReplayConflict
from .values import digest, json_text, missing
from .record_gates import classify_records, evaluate_gate
from .quality_reports import table_evidence
from .validation import validate_fields
from .sqlite_cdc import SqliteChangeCapture
from .sqlite_change_loader import SqliteChangeLoader
from .sqlite_source import validate_contracts, quoted, read_tables, logical_frame


@dataclass
class DatabaseJobConfig:
    source_path: Path
    database_path: Path
    schemas: dict
    date_formats: dict = field(default_factory=dict)
    owner_rules: list = field(default_factory=list)
    job_name: str = "foundation_database"

    def policy(self):
        return {"source_path": str(Path(self.source_path).resolve()),
                "database_path": str(Path(self.database_path).resolve()),
                "schemas": self.schemas, "date_formats": self.date_formats,
                "owner_rules": self.owner_rules, "version": "sqlite-trigger-cdc-v1"}


@dataclass
class DatabaseRun:
    run_id: str
    status: str
    previous_sequence: int | None
    sequence: int
    table_counts: dict
    event_count: int = 0
    operations: dict = field(default_factory=dict)
    recovered_after_commit: bool = False


class SqliteDatabasePipeline:
    def __init__(self, config, *, fault_hook=None, source_read_hook=None):
        self.config = deepcopy(config)
        self.config.source_path = Path(config.source_path).resolve()
        self.config.database_path = Path(config.database_path).resolve()
        if self.config.source_path == self.config.database_path:
            raise ValueError("Source and target SQLite paths must be distinct")
        if not isinstance(config.job_name, str) or not config.job_name:
            raise ValueError("Database job requires a name")
        validate_contracts(self.config.schemas)
        for table, schema in self.config.schemas.items():
            for column, rules in schema["columns"].items():
                if rules["dtype"] in {"date", "timestamp"} and column not in self.config.date_formats.get(table, {}):
                    raise ValueError(f"Date formats are required for {table}.{column}")
                if "foreign_key" in rules:
                    parent, key = rules["foreign_key"].split(".")
                    parent_schema = self.config.schemas.get(parent)
                    if parent_schema is None or key not in parent_schema["columns"]:
                        raise ValueError(f"Selected reference contract unavailable: {parent}.{key}")
                    if key != parent_schema["primary_key"] and not parent_schema["columns"][key].get("unique"):
                        raise ValueError(f"Reference key must be declared unique: {parent}.{key}")
        for rule in self.config.owner_rules:
            for table_key, column_keys in (("table", ("foreign_key", "owner_column")),
                                           ("reference_table", ("reference_key", "reference_owner_column"))):
                table = rule.get(table_key)
                if table not in self.config.schemas or any(rule.get(name) not in self.config.schemas[table]["columns"] for name in column_keys):
                    raise ValueError("Owner rule requires known tables and fields")
        self.capture = SqliteChangeCapture(self.config.source_path, self.config.schemas)
        self.change_loader = SqliteChangeLoader(self.config.schemas)
        self.policy = self.config.policy()
        self.policy_hash = digest(self.policy)
        self.fault_hook = fault_hook
        self.source_read_hook = source_read_hook

    def _connect(self):
        self.config.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.config.database_path, timeout=5)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _metadata(connection):
        connection.execute("CREATE TABLE IF NOT EXISTS _etl_db_jobs (job TEXT PRIMARY KEY,source_id TEXT NOT NULL,"
                           "policy TEXT NOT NULL,policy_hash TEXT NOT NULL,checkpoint INTEGER NOT NULL,"
                           "bootstrap_sequence INTEGER NOT NULL,target_digest TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS _etl_db_runs (run_id TEXT PRIMARY KEY,job TEXT NOT NULL,"
                           "at TEXT NOT NULL,status TEXT NOT NULL,summary TEXT NOT NULL,evidence TEXT NOT NULL,error TEXT)")
        connection.execute("CREATE TABLE IF NOT EXISTS _etl_db_events (job TEXT NOT NULL,sequence INTEGER NOT NULL,"
                           "event_digest TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(job,sequence))")

    def checkpoint(self):
        if not self.config.database_path.is_file():
            return None
        with closing(self._connect()) as connection:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='_etl_db_jobs'").fetchone():
                return None
            row = connection.execute("SELECT checkpoint FROM _etl_db_jobs WHERE job=?", (self.config.job_name,)).fetchone()
            return row[0] if row else None

    def _job(self, connection, source_id):
        row = connection.execute("SELECT source_id,policy_hash,checkpoint,bootstrap_sequence,target_digest,policy FROM _etl_db_jobs WHERE job=?",
                                 (self.config.job_name,)).fetchone()
        if row is not None:
            if row[0] != source_id or row[1] != self.policy_hash or row[5] != json_text(self.policy):
                raise ValueError("Target job source identity or policy changed")
            if type(row[2]) is not int or type(row[3]) is not int or not 0 <= row[3] <= row[2]:
                raise ReplayConflict("Target checkpoint metadata is invalid")
            audit = connection.execute("SELECT sequence,event_digest,payload FROM _etl_db_events WHERE job=? ORDER BY sequence",
                                       (self.config.job_name,)).fetchall()
            if [item[0] for item in audit] != list(range(row[3] + 1, row[2] + 1)) or any(
                digest(json.loads(payload)) != event_digest for sequence, event_digest, payload in audit
            ):
                raise ReplayConflict("Consumed event audit has a gap or changed payload")
            if row[4] != digest(self._target_layout(connection)):
                raise ValueError("Target table schema drift")
        return row

    def _target_layout(self, connection):
        result = {}
        for table in self.config.schemas:
            sql = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if sql is None:
                raise ValueError(f"Target table missing: {table}")
            indexes = []
            for item in connection.execute(f"PRAGMA index_list({quoted(table)})"):
                name = item[1].replace('"', '""')
                indexes.append((item, connection.execute(f'PRAGMA index_xinfo("{name}")').fetchall()))
            result[table] = {"sql": sql[0], "columns": connection.execute(f"PRAGMA table_info({quoted(table)})").fetchall(),
                             "foreign_keys": connection.execute(f"PRAGMA foreign_key_list({quoted(table)})").fetchall(),
                             "indexes": sorted(indexes)}
        return result

    def _create_business_tables(self, connection):
        self.change_loader.create_tables(connection)

    def _assess(self, tables):
        cleaner = CleaningEngine()
        before = {table: validate_fields(data, self.config.schemas[table], tables) for table, data in tables.items()}
        cleaned = {table: cleaner.clean(data, self.config.schemas[table], self.config.date_formats.get(table, {}))
                   for table, data in tables.items()}
        for table, result in cleaned.items():
            key = self.config.schemas[table]["primary_key"]
            for correction in result.corrections:
                if correction.column == key:
                    result.issues.append(CleaningIssue(correction.row_position, key, "primary_key_normalization_blocked", correction.original_value))
        frames = {table: result.data for table, result in cleaned.items()}
        after = {table: validate_fields(data, self.config.schemas[table], frames) for table, data in frames.items()}
        for rule in self.config.owner_rules:
            parent = frames[rule["reference_table"]]
            reference_key = rule["reference_key"]
            if parent[reference_key].duplicated().any():
                after[rule["table"]].batch_failures.append("owner_reference_keys_not_unique")
                continue
            owners = dict(zip(parent[reference_key], parent[rule["reference_owner_column"]]))
            child = frames[rule["table"]]
            for position in range(len(child)):
                reference = child[rule["foreign_key"]].iloc[position]
                owner = child[rule["owner_column"]].iloc[position]
                if not missing(reference) and not missing(owner) and (reference not in owners or missing(owners[reference]) or owner != owners[reference]):
                    after[rule["table"]].issues.append(CleaningIssue(position, rule["owner_column"], "reference_owner_mismatch", owner))
        evidence, passed = {}, True
        for table, result in cleaned.items():
            dispositions = classify_records(result.data, self.config.schemas[table], result.corrections,
                                             [*result.issues, *after[table].issues])
            gate = evaluate_gate(dispositions, batch_failures=after[table].batch_failures)
            passed = passed and gate.outcome == "pass"
            evidence[table] = table_evidence(tables[table], result, self.config.schemas[table], before[table], after[table], dispositions, gate)
            evidence[table].update({"issues_before": [asdict(item) for item in before[table].issues],
                                    "issues_after": [asdict(item) for item in after[table].issues],
                                    "cleaning_issues": [asdict(item) for item in result.issues],
                                    "corrections": [asdict(item) for item in result.corrections],
                                    "rows_before": tables[table].to_dict("records"), "rows_after": result.data.to_dict("records")})
        return frames, evidence, passed

    def _normalized_row(self, table, row):
        schema = self.config.schemas[table]
        if not isinstance(row, dict) or set(row) != set(schema["columns"]):
            raise ReplayConflict("Change image columns differ from the declared table")
        frame = logical_frame([tuple(row[column] for column in schema["columns"])], schema)
        result = CleaningEngine().clean(frame, schema, self.config.date_formats.get(table, {}))
        if any(item.column == schema["primary_key"] for item in result.corrections):
            raise ReplayConflict("Primary-key normalization is unsupported for tracked changes")
        return result.data.to_dict("records")[0]

    def _row_digest(self, table, row):
        return self.change_loader.row_digest(table, row)

    def _table_digest(self, table, frame):
        return self.change_loader.table_digest(table, frame)

    def _project(self, current, events):
        state = {table: {json_text(row[self.config.schemas[table]["primary_key"]]): row for row in data.to_dict("records")}
                 for table, data in current.items()}
        touched = {table: {} for table in state}
        for event in events:
            if event.table not in state or event.operation not in {"INSERT", "UPDATE", "DELETE"}:
                raise ReplayConflict("Unexpected captured table or operation")
            table, key = event.table, self.config.schemas[event.table]["primary_key"]
            if event.operation != "INSERT":
                old = self._normalized_row(table, event.old_row)
                token = json_text(event.old_key)
                if missing(event.old_key) or json_text(event.old_row[key]) != token or token not in state[table]:
                    raise ReplayConflict("Captured before-key does not match current target state")
                actual = self._normalized_row(table, state[table][token])
                if self._row_digest(table, old) != self._row_digest(table, actual):
                    raise ReplayConflict("Captured before-image differs from current target state")
                del state[table][token]
                touched[table][token] = event.old_key
            elif event.old_key is not None or event.old_row is not None:
                raise ReplayConflict("Insert event has an unexpected before-image")
            if event.operation != "DELETE":
                new = self._normalized_row(table, event.new_row)
                token = json_text(event.new_key)
                if missing(event.new_key) or json_text(event.new_row[key]) != token or token in state[table]:
                    raise ReplayConflict("Captured after-key conflicts with current target state")
                state[table][token] = event.new_row
                touched[table][token] = event.new_key
            elif event.new_key is not None or event.new_row is not None:
                raise ReplayConflict("Delete event has an unexpected after-image")
        frames = {table: logical_frame([tuple(row[column] for column in self.config.schemas[table]["columns"])
                                       for token, row in sorted(rows.items())], self.config.schemas[table])
                  for table, rows in state.items()}
        return frames, touched

    def _apply(self, connection, frames, touched=None):
        self.change_loader.apply(connection, frames, touched)

    def _run_record(self, connection, result, evidence, error=None):
        connection.execute("INSERT INTO _etl_db_runs VALUES(?,?,?,?,?,?,?)", (result.run_id, self.config.job_name,
                           datetime.now(timezone.utc).isoformat(), result.status, json_text(asdict(result)), json_text(evidence), error))

    def _failure_record(self, result, error, evidence):
        try:
            with closing(self._connect()) as connection:
                with connection:
                    self._metadata(connection)
                    result.status = "failed"
                    self._run_record(connection, result, evidence, f"{type(error).__name__}: {error}")
        except Exception:
            pass  # Preserve the original failure when the audit store is unavailable.

    def _committed_result(self, run_id, source_id):
        with closing(self._connect()) as connection:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='_etl_db_runs'").fetchone():
                return None
            row = connection.execute("SELECT r.summary,j.checkpoint,j.source_id,j.policy_hash FROM _etl_db_runs r "
                                     "JOIN _etl_db_jobs j ON r.job=j.job WHERE r.run_id=? AND r.status IN ('succeeded','no_changes')",
                                     (run_id,)).fetchone()
            if row:
                result = DatabaseRun(**json.loads(row[0]))
                if row[1:] == (result.sequence, source_id, self.policy_hash):
                    result.recovered_after_commit = True
                    return result
        return None

    def _verify_consumed_history(self, connection, snapshot, checkpoint, bootstrap_sequence):
        for event in snapshot.history:
            if bootstrap_sequence < event.sequence <= checkpoint:
                old = connection.execute("SELECT event_digest,payload FROM _etl_db_events WHERE job=? AND sequence=?",
                                         (self.config.job_name, event.sequence)).fetchone()
                if old != (event.fingerprint, json_text(asdict(event))):
                    raise ReplayConflict("Previously consumed event changed or audit evidence is missing")

    def _verify_existing_bootstrap(self, connection, job, snapshot):
        if snapshot.high_water < job[2]:
            raise ReplayConflict("Source high water precedes the committed target checkpoint")
        self._verify_consumed_history(connection, snapshot, job[2], job[3])
        row = connection.execute("SELECT run_id,status,summary,evidence FROM _etl_db_runs "
                                 "WHERE job=? AND status IN ('succeeded','no_changes') ORDER BY rowid DESC LIMIT 1",
                                 (self.config.job_name,)).fetchone()
        if row is None:
            raise ReplayConflict("Committed target quality evidence is missing")
        try:
            summary, evidence = json.loads(row[2]), json.loads(row[3])
            if (summary["run_id"] != row[0] or summary["status"] != row[1] or summary["sequence"] != job[2]
                    or evidence["source_id"] != snapshot.source_id or evidence["high_water"] != job[2]
                    or set(evidence["tables"]) != set(self.config.schemas)):
                raise ValueError("Committed evidence identity or sequence differs")
            expected = {}
            for table, schema in self.config.schemas.items():
                detail = evidence["tables"][table]
                rows = detail["rows_after"]
                if (not isinstance(rows, list) or detail["gate"]["outcome"] != "pass"
                        or any(not isinstance(item, dict) or set(item) != set(schema["columns"]) for item in rows)):
                    raise ValueError("Committed table evidence is incomplete")
                expected[table] = logical_frame([tuple(item[column] for column in schema["columns"]) for item in rows], schema)
            if summary["table_counts"] != {table: len(frame) for table, frame in expected.items()}:
                raise ValueError("Committed evidence row counts differ")
        except (KeyError, TypeError, ValueError) as error:
            raise ReplayConflict("Committed target quality evidence changed or is incomplete") from error
        current = read_tables(connection, self.config.schemas)
        cleaned, details, passed = self._assess(current)
        if (not passed or any(self._table_digest(table, current[table]) != self._table_digest(table, cleaned[table])
                              or self._table_digest(table, current[table]) != self._table_digest(table, expected[table])
                              for table in current)):
            raise ReplayConflict("Existing bootstrap target differs from its committed quality evidence")
        # A pending source interval is left for run_changes. A caught-up source
        # also proves that the target still represents the consistent snapshot.
        if snapshot.high_water == job[2]:
            source, details, passed = self._assess(snapshot.tables)
            if not passed or any(self._table_digest(table, source[table]) != self._table_digest(table, current[table]) for table in current):
                raise ReplayConflict("Existing bootstrap target differs from the caught-up source snapshot")
        return {table: len(frame) for table, frame in current.items()}

    def _execute(self, snapshot, previous_sequence, bootstrap):
        result = DatabaseRun(uuid4().hex, "running", previous_sequence, snapshot.high_water,
                             {table: len(data) for table, data in snapshot.tables.items()}, len(snapshot.events),
                             {operation: sum(item.operation == operation for item in snapshot.events) for operation in ("INSERT", "UPDATE", "DELETE")})
        evidence = {"source_id": snapshot.source_id, "high_water": snapshot.high_water,
                    "events": [asdict(item) for item in snapshot.events]}
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._metadata(connection)
                    job = self._job(connection, snapshot.source_id)
                    if bootstrap and job is not None:
                        counts = self._verify_existing_bootstrap(connection, job, snapshot)
                        connection.rollback()
                        return DatabaseRun(result.run_id, "already_bootstrapped", job[2], job[2],
                                           counts)
                    if not bootstrap and (job is None or job[2] != previous_sequence):
                        raise ValueError("Checkpoint changed; read source changes again")
                    if bootstrap:
                        for table in self.config.schemas:
                            if connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                                raise ValueError(f"Bootstrap requires fresh target tables: {table}")
                    frames, table_details, passed = self._assess(snapshot.tables)
                    evidence["tables"] = table_details
                    if not passed:
                        result.status = "stopped"
                        self._run_record(connection, result, evidence)
                        connection.commit()
                        return result
                    touched = None
                    if not bootstrap:
                        self._verify_consumed_history(connection, snapshot, previous_sequence, job[3])
                        projected, touched = self._project(read_tables(connection, self.config.schemas), snapshot.events)
                        projected_frames, projected_evidence, projected_passed = self._assess(projected)
                        evidence["projected_target"] = projected_evidence
                        if not projected_passed or any(self._table_digest(table, frames[table]) != self._table_digest(table, projected_frames[table]) for table in frames):
                            raise ReplayConflict("Journal changes do not reconcile to the consistent source snapshot")
                    if bootstrap:
                        self._create_business_tables(connection)
                    self._apply(connection, frames, touched)
                    if bootstrap:
                        connection.execute("INSERT INTO _etl_db_jobs VALUES(?,?,?,?,?,?,?)", (self.config.job_name, snapshot.source_id,
                                           json_text(self.policy), self.policy_hash, snapshot.high_water, snapshot.high_water, digest(self._target_layout(connection))))
                    else:
                        for event in snapshot.events:
                            old = connection.execute("SELECT event_digest,payload FROM _etl_db_events WHERE job=? AND sequence=?",
                                                     (self.config.job_name, event.sequence)).fetchone()
                            expected = (event.fingerprint, json_text(asdict(event)))
                            if old is not None and old != expected:
                                raise ReplayConflict("Replayed event differs from persisted evidence")
                            connection.execute("INSERT OR IGNORE INTO _etl_db_events VALUES(?,?,?,?)",
                                               (self.config.job_name, event.sequence, *expected))
                        connection.execute("UPDATE _etl_db_jobs SET checkpoint=? WHERE job=?", (snapshot.high_water, self.config.job_name))
                    result.status = "succeeded" if bootstrap or snapshot.events else "no_changes"
                    self._run_record(connection, result, evidence)
                    if self.fault_hook:
                        self.fault_hook("before_commit")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            if self.fault_hook:
                self.fault_hook("after_commit")
            return result
        except Exception as error:
            recovered = self._committed_result(result.run_id, snapshot.source_id) if self.config.database_path.exists() else None
            if recovered is not None:
                return recovered
            self._failure_record(result, error, evidence)
            raise

    def bootstrap(self):
        try:
            snapshot = self.capture.snapshot(after_read=self.source_read_hook)
        except Exception as error:
            self._failure_record(DatabaseRun(uuid4().hex, "failed", None, 0, {}), error, {"phase": "capture_snapshot_read"})
            raise
        return self._execute(snapshot, None, True)

    def run_changes(self):
        previous = self.checkpoint()
        if previous is None:
            raise ValueError("Bootstrap the target before consuming changes")
        try:
            snapshot = self.capture.changes_after(previous, after_read=self.source_read_hook)
        except Exception as error:
            self._failure_record(DatabaseRun(uuid4().hex, "failed", previous, previous, {}), error, {"phase": "capture_change_read"})
            raise
        return self._execute(snapshot, previous, False)
