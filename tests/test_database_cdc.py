"""Local snapshot handoff, strict multi-table CDC and atomic checkpoint recovery."""

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from governed_data_pipeline.database_pipeline import DatabaseJobConfig, SqliteDatabasePipeline
from governed_data_pipeline.loading import ReplayConflict
from governed_data_pipeline.sqlite_cdc import SqliteChangeCapture
from governed_data_pipeline.sqlite_change_loader import SqliteChangeLoader
from governed_data_pipeline.sqlite_source import ReadOnlySqliteExtractor


def contracts():
    return {
        "parents": {"primary_key": "id", "columns": {
            "id": {"dtype": "string", "required": True},
            "owner": {"dtype": "string", "required": True},
            "amount": {"dtype": "float", "min": 0},
            "active": {"dtype": "boolean", "required": True}}},
        "children": {"primary_key": "id", "columns": {
            "id": {"dtype": "string", "required": True},
            "parent_id": {"dtype": "string", "required": True, "foreign_key": "parents.id"},
            "owner": {"dtype": "string", "required": True},
            "amount": {"dtype": "float", "min": 0}}},
    }


class DatabaseCdcTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.source = Path(scratch.name) / "source.sqlite"
        self.target = Path(scratch.name) / "target.sqlite"
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("CREATE TABLE parents(id TEXT PRIMARY KEY NOT NULL,owner TEXT,amount REAL,active INTEGER);"
                                     "CREATE TABLE children(id TEXT PRIMARY KEY NOT NULL,parent_id TEXT,owner TEXT,amount REAL);"
                                     "INSERT INTO parents VALUES('P1','U1',10,1);"
                                     "INSERT INTO children VALUES('C1','P1','U1',5);")
        self.schemas = contracts()
        self.owner_rules = [{"table": "children", "reference_table": "parents", "foreign_key": "parent_id",
                             "reference_key": "id", "owner_column": "owner", "reference_owner_column": "owner"}]
        self.config = DatabaseJobConfig(self.source, self.target, self.schemas, owner_rules=self.owner_rules)
        self.capture = SqliteChangeCapture(self.source, self.schemas)
        self.capture.install()
        self.pipeline = SqliteDatabasePipeline(self.config)

    def mutate(self, statement, values=()):
        with closing(sqlite3.connect(self.source)) as connection:
            with connection:
                connection.execute(statement, values)

    def target_rows(self, table):
        with closing(sqlite3.connect(self.target)) as connection:
            return connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()

    def test_read_only_snapshot_preserves_string_keys_and_native_boolean_meaning(self):
        original = self.source.read_bytes()
        snapshot = ReadOnlySqliteExtractor(self.source, self.schemas).extract()
        self.assertEqual(snapshot.tables["parents"].id.tolist(), ["P1"])
        self.assertEqual(snapshot.tables["parents"].active.tolist(), [True])
        self.assertEqual(self.source.read_bytes(), original)
        missing = self.source.with_name("missing.sqlite")
        with self.assertRaises(FileNotFoundError):
            ReadOnlySqliteExtractor(missing, self.schemas).extract()
        self.assertFalse(missing.exists())

    def test_independent_change_loader_preserves_caller_commit_and_rollback(self):
        tables = ReadOnlySqliteExtractor(self.source, self.schemas).extract().tables
        loader = SqliteChangeLoader(self.schemas)
        with closing(sqlite3.connect(self.target)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(ValueError):
                loader.create_tables(connection)
            connection.execute("BEGIN IMMEDIATE")
            loader.create_tables(connection)
            loader.apply(connection, tables)
            self.assertTrue(connection.in_transaction)
            connection.rollback()
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='parents'").fetchone())
            connection.execute("BEGIN IMMEDIATE")
            loader.create_tables(connection)
            loader.apply(connection, tables)
            connection.commit()
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='_etl_db_jobs'").fetchone())
            final = {table: frame.copy(deep=True) for table, frame in tables.items()}
            final["parents"].loc[0, "amount"] = 42.0
            connection.execute("BEGIN IMMEDIATE")
            loader.apply(connection, final, {"parents": ["P1"], "children": []})
            self.assertEqual(connection.execute("SELECT amount FROM parents").fetchone()[0], 42.0)
            connection.rollback()
            self.assertEqual(connection.execute("SELECT amount FROM parents").fetchone()[0], 10.0)

    def test_bootstrap_insert_update_delete_and_unchanged_repeat(self):
        result = self.pipeline.bootstrap()
        self.assertEqual((result.status, result.sequence), ("succeeded", 0))
        self.assertEqual(self.pipeline.bootstrap().status, "already_bootstrapped")
        with closing(sqlite3.connect(self.source)) as connection:
            with connection:
                connection.execute("INSERT INTO parents VALUES('P2','U2',20,0)")
                connection.execute("INSERT INTO children VALUES('C2','P2','U2',7)")
                connection.execute("UPDATE parents SET amount=12 WHERE id='P1'")
                connection.execute("DELETE FROM children WHERE id='C1'")
        changed = self.pipeline.run_changes()
        self.assertEqual((changed.status, changed.event_count, changed.sequence), ("succeeded", 4, 4))
        self.assertEqual(self.target_rows("parents"), [("P1", "U1", 12.0, 1), ("P2", "U2", 20.0, 0)])
        self.assertEqual(self.target_rows("children"), [("C2", "P2", "U2", 7.0)])
        self.assertEqual(self.pipeline.run_changes().status, "no_changes")
        self.assertEqual(self.pipeline.checkpoint(), 4)
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM _etl_db_events").fetchone()[0], 4)
            evidence = json.loads(connection.execute("SELECT evidence FROM _etl_db_runs WHERE run_id=?", (changed.run_id,)).fetchone()[0])
        self.assertIn("profile_before", evidence["tables"]["parents"])
        self.assertIn("validation_after", evidence["tables"]["children"])

    def test_existing_bootstrap_rejects_changed_business_rows(self):
        self.pipeline.bootstrap()
        with closing(sqlite3.connect(self.target)) as connection:
            with connection:
                connection.execute("UPDATE parents SET amount=77 WHERE id='P1'")
        with self.assertRaisesRegex(ReplayConflict, "committed quality evidence"):
            self.pipeline.bootstrap()
        self.assertEqual(self.pipeline.checkpoint(), 0)

    def test_existing_bootstrap_rejects_changed_or_missing_evidence(self):
        result = self.pipeline.bootstrap()
        with closing(sqlite3.connect(self.target)) as connection:
            evidence = json.loads(connection.execute("SELECT evidence FROM _etl_db_runs WHERE run_id=?", (result.run_id,)).fetchone()[0])
            evidence["tables"]["parents"]["rows_after"][0]["amount"] = 77
            with connection:
                connection.execute("UPDATE _etl_db_runs SET evidence=? WHERE run_id=?", (json.dumps(evidence), result.run_id))
        with self.assertRaisesRegex(ReplayConflict, "committed quality evidence"):
            self.pipeline.bootstrap()
        with closing(sqlite3.connect(self.target)) as connection:
            with connection:
                connection.execute("DELETE FROM _etl_db_runs WHERE run_id=?", (result.run_id,))
        with self.assertRaisesRegex(ReplayConflict, "quality evidence is missing"):
            self.pipeline.bootstrap()
        self.assertEqual(self.pipeline.checkpoint(), 0)

    def test_existing_bootstrap_verifies_target_without_consuming_pending_changes(self):
        self.pipeline.bootstrap()
        self.mutate("UPDATE parents SET amount=12 WHERE id='P1'")
        result = self.pipeline.bootstrap()
        self.assertEqual((result.status, result.sequence), ("already_bootstrapped", 0))
        self.assertEqual(self.pipeline.checkpoint(), 0)
        self.assertEqual(self.target_rows("parents")[0][2], 10.0)
        self.assertEqual(self.capture.verify()[1], 1)
        self.assertEqual(self.pipeline.run_changes().sequence, 1)

    def test_existing_bootstrap_rejects_changed_consumed_source_history(self):
        self.pipeline.bootstrap()
        self.mutate("UPDATE parents SET amount=12 WHERE id='P1'")
        self.pipeline.run_changes()
        with closing(sqlite3.connect(self.source)) as connection:
            image = json.loads(connection.execute("SELECT new_row FROM _cdc_events WHERE sequence=1").fetchone()[0])
            image["amount"] = 77
            with connection:
                connection.execute("UPDATE _cdc_events SET new_row=? WHERE sequence=1", (json.dumps(image),))
        with self.assertRaisesRegex(ReplayConflict, "Previously consumed event changed"):
            self.pipeline.bootstrap()
        self.assertEqual(self.pipeline.checkpoint(), 1)


    def test_bootstrap_handoff_excludes_a_concurrently_committed_later_change(self):
        def insert_after_read():
            self.mutate("INSERT INTO parents VALUES('P2','U2',20,1)")
        bootstrap = SqliteDatabasePipeline(self.config, source_read_hook=insert_after_read).bootstrap()
        self.assertEqual(bootstrap.sequence, 0)
        self.assertEqual([row[0] for row in self.target_rows("parents")], ["P1"])
        self.assertEqual(self.pipeline.run_changes().event_count, 1)
        self.assertEqual([row[0] for row in self.target_rows("parents")], ["P1", "P2"])

    def test_invalid_child_and_orphan_delete_stop_without_advancing(self):
        self.pipeline.bootstrap()
        self.mutate("INSERT INTO children VALUES('C2','MISSING','U2',3)")
        result = self.pipeline.run_changes()
        self.assertEqual(result.status, "stopped")
        self.assertEqual(self.pipeline.checkpoint(), 0)
        self.assertEqual(len(self.target_rows("children")), 1)
        self.mutate("DELETE FROM children WHERE id='C2'")
        self.assertEqual(self.pipeline.run_changes().status, "succeeded")
        self.mutate("DELETE FROM parents WHERE id='P1'")
        checkpoint = self.pipeline.checkpoint()
        self.assertEqual(self.pipeline.run_changes().status, "stopped")
        self.assertEqual(self.pipeline.checkpoint(), checkpoint)
        self.assertEqual(len(self.target_rows("parents")), 1)

    def test_deleting_parent_and_children_in_one_source_transaction_is_safe(self):
        self.pipeline.bootstrap()
        with closing(sqlite3.connect(self.source)) as connection:
            with connection:
                connection.execute("DELETE FROM parents WHERE id='P1'")
                connection.execute("DELETE FROM children WHERE parent_id='P1'")
        self.assertEqual(self.pipeline.run_changes().status, "succeeded")
        self.assertEqual(self.target_rows("parents"), [])
        self.assertEqual(self.target_rows("children"), [])

    def test_owner_mismatch_stops_the_whole_bundle(self):
        self.pipeline.bootstrap()
        self.mutate("UPDATE children SET owner='OTHER' WHERE id='C1'")
        self.assertEqual(self.pipeline.run_changes().status, "stopped")
        self.assertEqual(self.pipeline.checkpoint(), 0)
        self.assertEqual(self.target_rows("children")[0][2], "U1")

    def test_primary_key_mutation_is_applied_as_delete_old_insert_new(self):
        self.pipeline.bootstrap()
        self.mutate("UPDATE children SET id='C9' WHERE id='C1'")
        self.assertEqual(self.pipeline.run_changes().status, "succeeded")
        self.assertEqual([row[0] for row in self.target_rows("children")], ["C9"])

    def test_primary_key_cleaning_corrections_are_blocked(self):
        self.pipeline.bootstrap()
        self.mutate("INSERT INTO parents VALUES(' P2 ','U2',20,1)")
        self.assertEqual(self.pipeline.run_changes().status, "stopped")
        self.assertEqual(self.pipeline.checkpoint(), 0)
        self.assertEqual(len(self.target_rows("parents")), 1)

    def test_capture_schema_and_policy_drift_fail(self):
        self.pipeline.bootstrap()
        config = deepcopy(self.config)
        config.owner_rules = []
        with self.assertRaisesRegex(ValueError, "policy changed"):
            SqliteDatabasePipeline(config).run_changes()
        self.mutate("ALTER TABLE parents ADD COLUMN unexpected TEXT")
        with self.assertRaisesRegex(ValueError, "schema/primary key|schema drift"):
            self.pipeline.run_changes()
        self.assertEqual(self.pipeline.checkpoint(), 0)

    def test_missing_capture_trigger_and_journal_are_rejected(self):
        self.pipeline.bootstrap()
        self.mutate("DROP TRIGGER _cdc_parents_update")
        with self.assertRaisesRegex(ValueError, "trigger missing"):
            self.pipeline.run_changes()
        self.mutate("DROP TABLE _cdc_events")
        with self.assertRaisesRegex(ValueError, "metadata/journal missing"):
            self.pipeline.run_changes()

    def test_source_identity_change_is_rejected(self):
        self.pipeline.bootstrap()
        self.mutate("UPDATE _cdc_meta SET source_id='different' WHERE singleton=1")
        with self.assertRaisesRegex(ValueError, "source identity"):
            self.pipeline.run_changes()

    def test_source_rollback_rolls_back_change_events_and_sequence(self):
        self.pipeline.bootstrap()
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute("BEGIN")
            connection.execute("INSERT INTO parents VALUES('P2','U2',20,1)")
            connection.rollback()
        self.assertEqual(self.capture.verify()[1], 0)
        self.assertEqual(self.pipeline.run_changes().status, "no_changes")
        self.mutate("INSERT INTO parents VALUES('P2','U2',20,1)")
        self.assertEqual(self.pipeline.run_changes().sequence, 1)

    def test_missing_unconsumed_event_is_a_retention_gap(self):
        self.pipeline.bootstrap()
        self.mutate("INSERT INTO parents VALUES('P2','U2',20,1)")
        self.mutate("INSERT INTO parents VALUES('P3','U3',30,1)")
        self.mutate("DELETE FROM _cdc_events WHERE sequence=1")
        with self.assertRaisesRegex(ValueError, "retention gap"):
            self.pipeline.run_changes()
        self.assertEqual(self.pipeline.checkpoint(), 0)

    def test_changed_consumed_event_conflicts_with_durable_audit_digest(self):
        self.pipeline.bootstrap()
        self.mutate("UPDATE parents SET amount=12 WHERE id='P1'")
        self.pipeline.run_changes()
        self.mutate("UPDATE _cdc_events SET new_row=json_set(new_row,'$.amount',999) WHERE sequence=1")
        with self.assertRaisesRegex(ReplayConflict, "consumed event changed"):
            self.pipeline.run_changes()
        self.assertEqual(self.pipeline.checkpoint(), 1)

    def test_consumed_target_audit_gap_is_rejected(self):
        self.pipeline.bootstrap()
        self.mutate("UPDATE parents SET amount=12 WHERE id='P1'")
        self.pipeline.run_changes()
        with closing(sqlite3.connect(self.target)) as connection:
            with connection:
                connection.execute("DELETE FROM _etl_db_events WHERE sequence=1")
        with self.assertRaisesRegex(ReplayConflict, "audit has a gap"):
            self.pipeline.run_changes()
        self.assertEqual(self.pipeline.checkpoint(), 1)

    def test_source_constraint_change_is_schema_drift(self):
        self.pipeline.bootstrap()
        self.mutate("CREATE UNIQUE INDEX source_owners ON parents(owner)")
        with self.assertRaisesRegex(ValueError, "schema drift"):
            self.pipeline.run_changes()

    def test_capture_read_failure_is_recorded_without_changing_checkpoint(self):
        self.pipeline.bootstrap()
        self.mutate("DROP TRIGGER _cdc_children_insert")
        with self.assertRaisesRegex(ValueError, "trigger missing"):
            self.pipeline.run_changes()
        with closing(sqlite3.connect(self.target)) as connection:
            row = connection.execute("SELECT status,error FROM _etl_db_runs ORDER BY rowid DESC LIMIT 1").fetchone()
        self.assertEqual(row[0], "failed")
        self.assertIn("trigger missing", row[1])
        self.assertEqual(self.pipeline.checkpoint(), 0)

    def test_target_tampering_is_not_hidden_by_an_unchanged_source(self):
        self.pipeline.bootstrap()
        with closing(sqlite3.connect(self.target)) as connection:
            with connection:
                connection.execute("UPDATE parents SET amount=999 WHERE id='P1'")
        with self.assertRaisesRegex(ReplayConflict, "reconcile"):
            self.pipeline.run_changes()
        self.assertEqual(self.pipeline.checkpoint(), 0)

    def test_before_commit_fault_rolls_back_rows_events_and_checkpoint(self):
        self.pipeline.bootstrap()
        self.mutate("INSERT INTO parents VALUES('P2','U2',20,1)")
        def fail(stage):
            if stage == "before_commit":
                raise OSError("simulated before commit")
        with self.assertRaisesRegex(OSError, "before commit"):
            SqliteDatabasePipeline(self.config, fault_hook=fail).run_changes()
        self.assertEqual(self.pipeline.checkpoint(), 0)
        self.assertEqual(len(self.target_rows("parents")), 1)
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM _etl_db_events").fetchone()[0], 0)
        self.assertEqual(self.pipeline.run_changes().status, "succeeded")

    def test_after_commit_fault_recovers_the_committed_result(self):
        self.pipeline.bootstrap()
        self.mutate("INSERT INTO parents VALUES('P2','U2',20,1)")
        def fail(stage):
            if stage == "after_commit":
                raise OSError("simulated after commit")
        result = SqliteDatabasePipeline(self.config, fault_hook=fail).run_changes()
        self.assertEqual((result.status, result.sequence, result.event_count), ("succeeded", 1, 1))
        self.assertTrue(result.recovered_after_commit)
        self.assertEqual(self.pipeline.checkpoint(), 1)
        self.assertEqual(self.pipeline.run_changes().status, "no_changes")

    def test_bootstrap_refuses_existing_business_tables(self):
        with closing(sqlite3.connect(self.target)) as connection:
            connection.execute("CREATE TABLE parents(id TEXT PRIMARY KEY)")
            connection.execute("INSERT INTO parents VALUES('UNRELATED')")
            connection.commit()
        with self.assertRaisesRegex(ValueError, "fresh target tables"):
            self.pipeline.bootstrap()
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertEqual(connection.execute("SELECT id FROM parents").fetchall(), [("UNRELATED",)])
        self.assertIsNone(self.pipeline.checkpoint())

    def test_bootstrap_before_commit_fault_can_be_retried_without_partial_tables(self):
        def fail(stage):
            if stage == "before_commit":
                raise OSError("bootstrap commit fault")
        with self.assertRaisesRegex(OSError, "bootstrap commit fault"):
            SqliteDatabasePipeline(self.config, fault_hook=fail).bootstrap()
        self.assertIsNone(self.pipeline.checkpoint())
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='parents'").fetchone())
        self.assertEqual(self.pipeline.bootstrap().status, "succeeded")

    def test_invalid_initial_bundle_retains_evidence_without_creating_business_tables(self):
        self.mutate("UPDATE children SET parent_id='MISSING' WHERE id='C1'")
        result = self.pipeline.bootstrap()
        self.assertEqual(result.status, "stopped")
        self.assertIsNone(self.pipeline.checkpoint())
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='parents'").fetchone())
            evidence = json.loads(connection.execute("SELECT evidence FROM _etl_db_runs WHERE run_id=?", (result.run_id,)).fetchone()[0])
        self.assertEqual(evidence["tables"]["children"]["gate"]["outcome"], "stop")


class CompositeDatabaseCursorTests(unittest.TestCase):
    def test_date_and_timestamp_bounds_require_exact_storage_text(self):
        from datetime import date, datetime
        with tempfile.TemporaryDirectory() as scratch:
            source = Path(scratch) / "cursor.sqlite"
            with closing(sqlite3.connect(source)) as connection:
                connection.executescript("CREATE TABLE observations(id TEXT PRIMARY KEY NOT NULL,observed TEXT,day TEXT);"
                                         "INSERT INTO observations VALUES('A','2026-10-06T10:00:00','2026-10-06');"
                                         "INSERT INTO observations VALUES('B','2026-10-06T10:00:00','2026-10-06');")
            schema = {"observations": {"primary_key": "id", "columns": {"id": {"dtype": "string", "required": True},
                        "observed": {"dtype": "timestamp", "required": True}, "day": {"dtype": "date", "required": True}}}}
            extractor = ReadOnlySqliteExtractor(source, schema)
            for column, native in (("observed", datetime(2026, 10, 6, 10)), ("day", date(2026, 10, 6))):
                for parameter in ("after", "upper_bound"):
                    with self.subTest(column=column, parameter=parameter):
                        with self.assertRaisesRegex(ValueError, "source storage text"):
                            extractor.extract_incremental("observations", column, "id", **{parameter: (native, "A")})
                text = native.isoformat()
                result = extractor.extract_incremental("observations", column, "id", after=(text, "A"), upper_bound=(text, "B"))
                self.assertEqual(result.data.id.tolist(), ["B"])


    def test_timestamp_ties_continue_at_unique_key_and_respect_upper_bound(self):
        with tempfile.TemporaryDirectory() as scratch:
            source = Path(scratch) / "cursor.sqlite"
            with closing(sqlite3.connect(source)) as connection:
                connection.executescript("CREATE TABLE observations(id TEXT PRIMARY KEY NOT NULL,observed TEXT);"
                                         "INSERT INTO observations VALUES('A','2026-10-06T10:00:00');"
                                         "INSERT INTO observations VALUES('B','2026-10-06T10:00:00');"
                                         "INSERT INTO observations VALUES('C','2026-10-06T11:00:00');")
            schema = {"observations": {"primary_key": "id", "columns": {"id": {"dtype": "string", "required": True},
                        "observed": {"dtype": "timestamp", "required": True}}}}
            extractor = ReadOnlySqliteExtractor(source, schema)
            original = source.read_bytes()
            first = extractor.extract_incremental("observations", "observed", "id", upper_bound=("2026-10-06T10:00:00", "A"))
            self.assertEqual(first.data.id.tolist(), ["A"])
            second = extractor.extract_incremental("observations", "observed", "id", after=first.candidate_cursor,
                                                   upper_bound=("2026-10-06T10:00:00", "B"))
            self.assertEqual(second.data.id.tolist(), ["B"])
            third = extractor.extract_incremental("observations", "observed", "id", after=second.candidate_cursor)
            self.assertEqual(third.data.id.tolist(), ["C"])
            self.assertEqual(third.upper_bound, ("2026-10-06T11:00:00", "C"))
            self.assertEqual(source.read_bytes(), original)
            with self.assertRaisesRegex(ValueError, "unique tie-breaker"):
                extractor.extract_incremental("observations", "observed", "observed")


if __name__ == "__main__":
    unittest.main()
