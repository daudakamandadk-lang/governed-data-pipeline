"""Standalone engine contracts and SQLite schema/replay boundaries."""

from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import pandas as pd

from governed_data_pipeline.cleaning import CleaningEngine
from governed_data_pipeline.loading import IdempotentSqliteLoader, ReplayConflict
from governed_data_pipeline.profiling import profile_data
from governed_data_pipeline.validation import validate_fields, validate_schema


def schema():
    return {
        "primary_key": "id",
        "columns": {
            "id": {"dtype": "integer", "required": True},
            "code": {"dtype": "string", "unique": True},
            "amount": {"dtype": "float"},
        },
    }


class SqliteContractTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.path = Path(scratch.name) / "target.db"
        self.loader = IdempotentSqliteLoader(self.path)

    def query(self, sql):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(sql).fetchall()

    def create_target(self, sql):
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.executescript(sql)

    def test_declared_unique_conflict_rolls_back_the_entire_later_batch(self):
        self.loader.load(pd.DataFrame({"id": [1], "code": ["A"]}), "records", schema())
        batch = pd.DataFrame({"id": [2, 3], "code": ["B", "A"]})
        with self.assertRaisesRegex(ReplayConflict, "unique"):
            self.loader.load(batch, "records", schema())
        self.assertEqual(self.query("SELECT id,code FROM records"), [(1, "A")])
        replay = self.loader.load(pd.DataFrame({"id": [1], "code": ["A"]}), "records", schema())
        self.assertEqual((replay.inserted, replay.reused), (0, 1))

    def test_optional_columns_have_stable_structure_and_alignment(self):
        first = pd.DataFrame({"band": ["low"], "id": [1]})
        snapshot = first.copy(deep=True)
        result = self.loader.load(first, "records", schema())
        self.assertTrue(self.loader.reconcile(result, first, schema(), ["amount"]).passed)
        pd.testing.assert_frame_equal(first, snapshot)
        self.assertEqual(self.query("SELECT id,code,amount,band FROM records"), [(1, None, None, "low")])

        second = pd.DataFrame({"amount": [12.5], "band": ["high"], "code": ["B"], "id": [2]})
        result = self.loader.load(second, "records", schema())
        self.assertTrue(self.loader.reconcile(result, second, schema(), ["amount"]).passed)
        reordered = second[["code", "id", "band", "amount"]]
        replay = self.loader.load(reordered, "records", schema())
        self.assertEqual((replay.inserted, replay.reused), (0, 1))
        self.assertTrue(self.loader.reconcile(replay, reordered, schema(), ["amount"]).passed)
        self.assertEqual(self.query("SELECT id,code,amount,band FROM records ORDER BY id"),
                         [(1, None, None, "low"), (2, "B", 12.5, "high")])

    def test_optional_unique_nulls_can_repeat(self):
        result = self.loader.load(pd.DataFrame({"id": [1, 2]}), "records", schema())
        self.assertEqual(result.inserted, 2)

    def test_missing_required_fields_are_rejected_before_database_creation(self):
        contract = schema()
        contract["columns"]["code"]["required"] = True
        for frame in (pd.DataFrame({"id": [1]}), pd.DataFrame({"id": [1], "code": [None]}),
                      pd.DataFrame({"id": [1], "code": ["   "]})):
            with self.subTest(frame=frame), self.assertRaisesRegex(ValueError, "Required target"):
                self.loader.load(frame, "records", contract)
        self.assertFalse(self.path.exists())

    def test_existing_target_without_declared_uniqueness_is_rejected(self):
        self.create_target("CREATE TABLE records (id INTEGER PRIMARY KEY NOT NULL, code TEXT, amount REAL);")
        with self.assertRaisesRegex(ValueError, "unique constraints"):
            self.loader.load(pd.DataFrame({"id": [1], "code": ["A"]}), "records", schema())
        self.assertEqual(self.query("SELECT COUNT(*) FROM records"), [(0,)])

    def test_composite_primary_key_does_not_satisfy_the_single_key_contract(self):
        self.create_target("CREATE TABLE records (id INTEGER NOT NULL, code TEXT UNIQUE, amount REAL, PRIMARY KEY(id,code));")
        with self.assertRaisesRegex(ValueError, "primary-key constraint"):
            self.loader.load(pd.DataFrame({"id": [1], "code": ["A"]}), "records", schema())
        self.assertEqual(self.query("SELECT COUNT(*) FROM records"), [(0,)])

    def test_partial_uniqueness_is_rejected(self):
        self.create_target("CREATE TABLE records (id INTEGER PRIMARY KEY NOT NULL, code TEXT, amount REAL);"
                           "CREATE UNIQUE INDEX some_codes ON records(code) WHERE amount > 0;")
        with self.assertRaisesRegex(ValueError, "unique constraints"):
            self.loader.load(pd.DataFrame({"id": [1], "code": ["A"]}), "records", schema())

    def test_binary_unique_index_can_implement_the_declared_constraint(self):
        self.create_target("CREATE TABLE records (id INTEGER PRIMARY KEY NOT NULL, code TEXT, amount REAL);"
                           "CREATE UNIQUE INDEX all_codes ON records(code);")
        result = self.loader.load(pd.DataFrame({"id": [1], "code": ["A"]}), "records", schema())
        self.assertEqual(result.inserted, 1)


class StandaloneFieldContractTests(unittest.TestCase):
    def test_primary_key_validation_is_independent_of_classification(self):
        result = validate_fields(pd.DataFrame({"id": [1, 1]}), schema())
        self.assertFalse(result.passed)
        self.assertEqual([(issue.row_position, issue.column, issue.code) for issue in result.issues],
                         [(0, "id", "duplicate_primary_key"), (1, "id", "duplicate_primary_key")])

    def date_contract(self, **rules):
        contract = schema()
        contract["columns"]["event_date"] = {"dtype": "date", **rules}
        return contract

    def test_datetime_and_timestamp_text_are_preserved_when_truncation_is_blocked(self):
        values = [datetime(2024, 1, 1, 12, 34, 56), "2024-01-02 12:34:56",
                  pd.Timestamp("2024-01-03 00:00:00.000000001")]
        frame = pd.DataFrame({"id": [1, 2, 3], "event_date": pd.Series(values, dtype=object)})
        snapshot = frame.copy(deep=True)
        cleaned = CleaningEngine().clean(frame, self.date_contract(),
                                                {"event_date": "%Y-%m-%d %H:%M:%S"})
        pd.testing.assert_frame_equal(frame, snapshot)
        pd.testing.assert_frame_equal(cleaned.data, snapshot)
        self.assertEqual(cleaned.corrected_cells, 0)
        self.assertEqual([issue.code for issue in cleaned.issues], ["date_time_truncation_blocked"] * 3)
        self.assertFalse(validate_fields(cleaned.data, self.date_contract()).passed)

    def test_explicit_truncation_policy_produces_a_documented_correction(self):
        frame = pd.DataFrame({"id": [1], "event_date": ["2024-01-01 12:34:56"]})
        contract = self.date_contract(allow_time_truncation=True)
        cleaned = CleaningEngine().clean(frame, contract,
                                                {"event_date": "%Y-%m-%d %H:%M:%S"})
        self.assertEqual(cleaned.data.event_date.iloc[0], "2024-01-01")
        self.assertEqual(cleaned.corrections[0].original_value, "2024-01-01 12:34:56")
        self.assertFalse(cleaned.issues)
        self.assertTrue(validate_fields(cleaned.data, contract).passed)

    def test_truncation_flag_must_be_boolean_and_applies_only_to_dates(self):
        for dtype, flag in (("date", "true"), ("date", 1), ("timestamp", True)):
            contract = self.date_contract(allow_time_truncation=flag)
            contract["columns"]["event_date"]["dtype"] = dtype
            with self.subTest(dtype=dtype, flag=flag):
                with self.assertRaisesRegex(ValueError, "allow_time_truncation"):
                    validate_schema(contract)
                with self.assertRaisesRegex(ValueError, "allow_time_truncation"):
                    CleaningEngine().clean(pd.DataFrame({"id": [1]}), contract)


class StandaloneProfilerTests(unittest.TestCase):
    def test_booleans_are_categorical_and_profiling_preserves_the_input(self):
        data = pd.DataFrame({"flag": pd.Series([True, False, True, pd.NA], dtype="boolean")})
        snapshot = data.copy(deep=True)
        field = profile_data(data)["fields"]["flag"]
        self.assertNotIn("numeric", field)
        self.assertEqual(field["missing"], 1)
        self.assertEqual(field["categorical"]["top_values"][True], 2)
        pd.testing.assert_frame_equal(data, snapshot)

    def test_empty_nullable_columns_produce_a_profile(self):
        data = pd.DataFrame({"number": pd.Series(dtype="Int64"), "flag": pd.Series(dtype="boolean"),
                             "when": pd.Series(dtype="datetime64[ns]")})
        result = profile_data(data)
        self.assertEqual(result["rows"], 0)
        self.assertEqual(result["fields"]["number"]["numeric"]["count"], 0)
        self.assertEqual(result["fields"]["flag"]["categorical"]["top_values"], {})
        self.assertIsNone(result["fields"]["when"]["date"]["range_days"])
        self.assertTrue(all(item["missing_pct"] == 0.0 for item in result["fields"].values()))


if __name__ == "__main__":
    unittest.main()
