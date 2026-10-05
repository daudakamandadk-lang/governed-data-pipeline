"""Durable run events, policy snapshots, quarantine and correction history."""

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import json

from .values import json_text
from .loading import ReplayConflict


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class RunJournal:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        with closing(self.connect()) as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS etl_jobs (
                    job TEXT PRIMARY KEY, identity TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS etl_runs (
                    run_id TEXT PRIMARY KEY, job TEXT, started_at TEXT,
                    finished_at TEXT, status TEXT, policy TEXT, summary TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS etl_events (
                    event_id INTEGER PRIMARY KEY, run_id TEXT, at TEXT,
                    stage TEXT, status TEXT, details TEXT);
                CREATE TABLE IF NOT EXISTS etl_quarantine (
                    batch_id TEXT, row_position INTEGER, first_run_id TEXT,
                    disposition TEXT, reasons TEXT, original TEXT, cleaned TEXT,
                    PRIMARY KEY(batch_id, row_position));
                CREATE TABLE IF NOT EXISTS etl_corrections (
                    run_id TEXT, row_position INTEGER, column_name TEXT,
                    reason TEXT, original TEXT, cleaned TEXT,
                    PRIMARY KEY(run_id, row_position, column_name, reason));
            ''')

    def connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.database_path, timeout=5)

    def start(self, run_id, job, policy):
        # Bind this job to its source, target and watermark store. A different
        # source cannot accidentally continue the old job's progress.
        identity = json_text({key: policy[key] for key in (
            "source", "target_table", "watermark_column", "watermark_path"
        )})
        with closing(self.connect()) as connection:
            with connection:
                old = connection.execute("SELECT identity FROM etl_jobs WHERE job=?", (job,)).fetchone()
                if old is not None and old[0] != identity:
                    raise ValueError("Job identity changed; use a distinct job and watermark store")
                for other_job, other_identity in connection.execute("SELECT job,identity FROM etl_jobs"):
                    if other_job != job and json.loads(other_identity)["watermark_path"] == policy["watermark_path"]:
                        raise ValueError("Each job requires its own watermark store")
                connection.execute("INSERT OR IGNORE INTO etl_jobs VALUES (?,?)", (job, identity))
                connection.execute("INSERT INTO etl_runs VALUES (?,?,?,?,?,?,?,?)",
                                   (run_id, job, utc_now(), None, "running", json_text(policy), None, None))

    def event(self, run_id, stage, status, details=None):
        with closing(self.connect()) as connection:
            with connection:
                connection.execute("INSERT INTO etl_events(run_id,at,stage,status,details) VALUES (?,?,?,?,?)",
                                   (run_id, utc_now(), stage, status, json_text(details or {})))

    def finish(self, run_id, status, summary=None, error=None):
        with closing(self.connect()) as connection:
            with connection:
                connection.execute("UPDATE etl_runs SET finished_at=?,status=?,summary=?,error=? WHERE run_id=?",
                                   (utc_now(), status, json_text(summary or {}), error, run_id))

    @staticmethod
    def quarantine_rows(batch_id, original, cleaned, dispositions, batch_failures):
        rows = []
        for record in dispositions:
            if record.disposition in {"quarantine", "reject"} or batch_failures:
                position = record.row_position
                disposition = record.disposition if record.disposition == "reject" else "quarantine"
                reasons = list(dict.fromkeys(record.reasons + list(batch_failures)))
                rows.append((batch_id, position, disposition, json_text(reasons),
                             json_text(original.iloc[position].to_dict()),
                             json_text(cleaned.iloc[position].to_dict())))
        return rows

    def persist(self, run_id, batch_id, original, cleaned, dispositions, batch_failures=()):
        rows = self.quarantine_rows(batch_id, original, cleaned.data, dispositions, batch_failures)
        with closing(self.connect()) as connection:
            with connection:
                for row in rows:
                    old = connection.execute(
                        "SELECT batch_id,row_position,disposition,reasons,original,cleaned FROM etl_quarantine "
                        "WHERE batch_id=? AND row_position=?", row[:2]
                    ).fetchone()
                    if old is not None and old != row:
                        raise ReplayConflict("A quarantine observation changed during replay")
                    connection.execute("INSERT OR IGNORE INTO etl_quarantine VALUES (?,?,?,?,?,?,?)",
                                       (row[0], row[1], run_id, *row[2:]))
                for correction in cleaned.corrections:
                    item = asdict(correction)
                    connection.execute("INSERT OR IGNORE INTO etl_corrections VALUES (?,?,?,?,?,?)", (
                        run_id, item["row_position"], item["column"], item["reason"],
                        json_text(item["original_value"]), json_text(item["cleaned_value"]),
                    ))
        return rows

    def verify_quarantine(self, batch_id, expected):
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT batch_id,row_position,disposition,reasons,original,cleaned FROM etl_quarantine "
                "WHERE batch_id=? ORDER BY row_position", (batch_id,)
            ).fetchall()
        return rows == sorted(expected, key=lambda row: row[1])
