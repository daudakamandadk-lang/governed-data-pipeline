"""Failures after commit, optional comparisons and unambiguous band policies."""

from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from governed_data_pipeline.pipeline import GovernedPipeline, RunFinalizationError
from governed_data_pipeline.transformation import BandRule, BandTransformer
from governed_data_pipeline.demo import example_config, sample_transactions
from governed_data_pipeline.validation import validate_fields


class FinalizationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.config = example_config(workspace=self.scratch.name)
        self.config.source.parent.mkdir(parents=True)
        sample_transactions().to_csv(self.config.source, index=False)
        self.pipeline = GovernedPipeline(self.config)

    def query(self, sql):
        with closing(sqlite3.connect(self.config.database_path)) as connection:
            return connection.execute(sql).fetchall()

    def test_transient_finish_failure_retries_only_finish_preserving_counts(self):
        finish = self.pipeline.journal.finish
        finish_calls = []

        def fail_once(*args):
            finish_calls.append(args)
            if len(finish_calls) == 1:
                raise OSError("temporary audit failure after commit")
            return finish(*args)

        with self.assertLogs("governed_data_pipeline.pipeline", level="WARNING"), \
             patch.object(self.pipeline.journal, "finish", side_effect=fail_once), \
             patch.object(self.pipeline.extractor, "extract", wraps=self.pipeline.extractor.extract) as extract, \
             patch.object(self.pipeline.loader, "load", wraps=self.pipeline.loader.load) as load:
            result = self.pipeline.run()
        self.assertEqual((result.status, result.extracted, result.inserted, result.reused),
                         ("succeeded", 6, 6, 0))
        self.assertEqual((extract.call_count, load.call_count, len(finish_calls)), (1, 1, 2))
        self.assertEqual(finish_calls[0], finish_calls[1])
        self.assertEqual(self.query("SELECT status FROM etl_runs"), [("succeeded",)])
        recorded = json.loads(self.query("SELECT summary FROM etl_runs")[0][0])
        self.assertEqual(recorded, asdict(result))
        self.assertEqual(self.query("SELECT COUNT(*) FROM transactions"), [(6,)])

    def test_sqlite_busy_finish_is_also_retried_without_reloading(self):
        finish = self.pipeline.journal.finish
        with self.assertLogs("governed_data_pipeline.pipeline", level="WARNING"), \
             patch.object(self.pipeline.journal, "finish", side_effect=[
                sqlite3.OperationalError("database is locked"), None]) as finalization, \
             patch.object(self.pipeline.extractor, "extract", wraps=self.pipeline.extractor.extract) as extract:
            result = self.pipeline.run()
        self.assertEqual((result.status, result.inserted, extract.call_count), ("succeeded", 6, 1))
        self.assertEqual(finalization.call_count, 2)
        # The simulated final write above had no persistence; recovery records
        # the original summary directly instead of beginning a different run.
        finish(result.run_id, result.status, asdict(result))
        self.assertEqual(self.query("SELECT status FROM etl_runs"), [("succeeded",)])

    def test_exhausted_finalization_keeps_completed_result_and_committed_progress(self):
        with self.assertLogs("governed_data_pipeline.pipeline", level="WARNING"), \
             patch.object(self.pipeline.journal, "finish", side_effect=OSError("audit unavailable")) as finish, \
             patch.object(self.pipeline.extractor, "extract", wraps=self.pipeline.extractor.extract) as extract:
            with self.assertRaises(RunFinalizationError) as caught:
                self.pipeline.run()
        error = caught.exception
        result = error.completed_run
        self.assertEqual((result.status, result.extracted, result.inserted), ("succeeded", 6, 6))
        self.assertEqual((error.attempts, finish.call_count, extract.call_count), (2, 2, 1))
        self.assertIsInstance(error.__cause__, OSError)
        self.assertIn("were not rolled back", str(error))
        self.assertEqual(self.query("SELECT status FROM etl_runs"), [("running",)])
        self.assertEqual(self.query("SELECT COUNT(*) FROM transactions"), [(6,)])
        self.assertTrue(self.config.watermark_path.exists())
        self.pipeline.journal.finish(result.run_id, result.status, asdict(result))
        self.assertEqual(self.query("SELECT status FROM etl_runs"), [("succeeded",)])
        self.assertEqual(GovernedPipeline(self.config).run().status, "no_new_rows")

    def test_nontransient_finish_failure_reports_terminal_result_without_retry(self):
        with patch.object(self.pipeline.journal, "finish", side_effect=ValueError("invalid journal summary")) as finish:
            with self.assertRaises(RunFinalizationError) as caught:
                self.pipeline.run()
        self.assertEqual((finish.call_count, caught.exception.attempts), (1, 1))
        self.assertEqual(caught.exception.completed_run.inserted, 6)
        self.assertEqual(self.query("SELECT status FROM etl_runs"), [("running",)])

    def test_commit_success_event_failure_does_not_reextract_committed_batch(self):
        event = self.pipeline.journal.event

        def fail_commit_event(run_id, stage, status, details=None):
            if stage == "commit" and status == "succeeded":
                raise OSError("event unavailable after progress advanced")
            return event(run_id, stage, status, details)

        with self.assertLogs("governed_data_pipeline.pipeline", level="WARNING") as logs, \
             patch.object(self.pipeline.journal, "event", side_effect=fail_commit_event), \
             patch.object(self.pipeline.extractor, "extract", wraps=self.pipeline.extractor.extract) as extract:
            result = self.pipeline.run()
        self.assertEqual((result.status, result.extracted, result.inserted, extract.call_count),
                         ("succeeded", 6, 6, 1))
        self.assertEqual(self.query("SELECT status FROM etl_runs"), [("succeeded",)])
        self.assertTrue(self.config.watermark_path.exists())
        self.assertIn("success-event recording failed", logs.output[0])

    def test_stopped_run_finalization_retry_preserves_quarantine_and_never_loads(self):
        sample_transactions(True).to_csv(self.config.source, index=False)
        finish = self.pipeline.journal.finish
        calls = []

        def fail_once(*args):
            calls.append(args)
            if len(calls) == 1:
                raise OSError("audit temporarily unavailable")
            finish(*args)

        with self.assertLogs("governed_data_pipeline.pipeline", level="WARNING"), \
             patch.object(self.pipeline.journal, "finish", side_effect=fail_once), \
             patch.object(self.pipeline.extractor, "extract", wraps=self.pipeline.extractor.extract) as extract, \
             patch.object(self.pipeline.loader, "load", wraps=self.pipeline.loader.load) as load:
            result = self.pipeline.run()
        self.assertEqual((result.status, result.extracted, result.quarantined), ("stopped", 6, 3))
        self.assertEqual((extract.call_count, load.call_count), (1, 0))
        self.assertFalse(self.config.watermark_path.exists())
        self.assertEqual(self.query("SELECT COUNT(*) FROM etl_quarantine"), [(3,)])

    def test_quality_evidence_is_persisted_before_loading(self):
        load = self.pipeline.loader.load

        def inspect_then_load(*args):
            recorded = self.query(
                "SELECT details FROM etl_events WHERE stage='quality_report' AND status='evidence'")
            self.assertEqual(len(recorded), 1)
            evidence = json.loads(recorded[0][0])
            self.assertEqual(evidence["profile_before"]["rows"], 6)
            self.assertEqual(evidence["profile_after"]["rows"], 6)
            self.assertGreater(evidence["corrected_cells"], 0)
            self.assertTrue(evidence["validation_after"]["contract_passed"])
            self.assertEqual(evidence["validation_after"]["source_accuracy"], "not_assessed")
            return load(*args)

        with patch.object(self.pipeline.loader, "load", side_effect=inspect_then_load):
            self.assertEqual(self.pipeline.run().status, "succeeded")


def comparison_schema(*, required_right=False, condition=False):
    schema = {
        "primary_key": "id",
        "columns": {
            "id": {"dtype": "integer", "required": True},
            "low": {"dtype": "float"},
            "high": {"dtype": "float", "required": required_right},
            "flag": {"dtype": "boolean"},
        },
        "comparisons": [{"left": "low", "right": "high", "operator": "le", "code": "range_order"}],
    }
    if condition:
        schema["comparisons"][0]["when"] = {"column": "flag", "equals": True}
    return schema


class OptionalComparisonTests(unittest.TestCase):
    def test_absent_optional_operand_matches_present_null_operand(self):
        schema = comparison_schema()
        absent = pd.DataFrame({"id": [1, 2], "low": [5, 10]})
        present = absent.assign(high=None)
        for data in (absent, present):
            with self.subTest(columns=list(data.columns)):
                self.assertTrue(validate_fields(data, schema).passed)
        self.assertEqual(list(absent.columns), ["id", "low"])

    def test_absent_optional_condition_matches_null_condition(self):
        schema = comparison_schema(condition=True)
        absent = pd.DataFrame({"id": [1], "low": [10], "high": [5]})
        self.assertTrue(validate_fields(absent, schema).passed)
        self.assertTrue(validate_fields(absent.assign(flag=None), schema).passed)
        result = validate_fields(absent.assign(flag=True), schema)
        self.assertEqual([issue.code for issue in result.issues], ["range_order"])

    def test_absent_optional_left_and_empty_batches_are_not_structural_errors(self):
        schema = comparison_schema()
        for data in (pd.DataFrame({"id": [1], "high": [5]}),
                     pd.DataFrame({"id": pd.Series([], dtype="int64")})):
            with self.subTest(rows=len(data)):
                self.assertTrue(validate_fields(data, schema).passed)

    def test_missing_required_comparison_field_still_blocks_the_batch(self):
        result = validate_fields(pd.DataFrame({"id": [1], "low": [5]}),
                                 comparison_schema(required_right=True))
        self.assertEqual(result.batch_failures, ["missing_required_column:high"])
        self.assertFalse(result.passed)


class BandPolicyTests(unittest.TestCase):
    def test_malformed_bounds_and_labels_are_rejected_at_construction(self):
        cases = [
            (True, 5, "yes"), (0, False, "yes"), (np.bool_(True), 5, "yes"),
            (float("nan"), 5, "yes"), (0, float("nan"), "yes"),
            (float("-inf"), 5, "yes"), (0, float("inf"), "yes"),
            ("0", 5, "yes"), (5, 5, "yes"), (10, 5, "yes"),
            (0, 5, ""), (0, 5, "  "), (0, 5, None),
        ]
        for low, high, label in cases:
            with self.subTest(low=low, high=high, label=label), self.assertRaises(ValueError):
                BandRule(low, high, label)

    def test_overlapping_and_unbounded_overlaps_are_rejected(self):
        cases = [
            [BandRule(0, 100, "a"), BandRule(50, 150, "b")],
            [BandRule(0, 100, "a"), BandRule(20, 30, "b")],
            [BandRule(None, 100, "a"), BandRule(50, None, "b")],
            [BandRule(None, None, "a"), BandRule(200, None, "b")],
        ]
        for rules in cases:
            with self.subTest(rules=rules), self.assertRaisesRegex(ValueError, "overlap"):
                BandTransformer("amount", "band", rules)

    def test_adjacent_unordered_bands_have_deterministic_boundary_labels(self):
        transformer = BandTransformer("amount", "band", [
            BandRule(100, None, "high"), BandRule(None, 100, "low")])
        result = transformer.transform(pd.DataFrame({"amount": [-1, 0, 99.5, 100, 150]}))
        self.assertEqual(result.band.tolist(), ["low", "low", "low", "high", "high"])

    def test_gaps_remain_visible_without_mutating_input(self):
        transformer = BandTransformer("amount", "band", [
            BandRule(0, 10, "small"), BandRule(20, 30, "large")])
        data = pd.DataFrame({"amount": [5, 15, 25]})
        original = data.copy()
        result = transformer.transform(data)
        self.assertEqual(result.band.iloc[0], "small")
        self.assertTrue(pd.isna(result.band.iloc[1]))
        self.assertEqual(result.band.iloc[2], "large")
        pd.testing.assert_frame_equal(data, original)

    def test_contains_rejects_nonfinite_boolean_and_nonnumeric_values(self):
        rule = BandRule(None, None, "numeric")
        for value in (True, np.bool_(True), float("nan"), float("inf"), "5", None):
            with self.subTest(value=value):
                self.assertFalse(rule.contains(value))
        self.assertTrue(rule.contains(5))

    def test_invalid_pipeline_band_policy_fails_before_creating_database(self):
        with tempfile.TemporaryDirectory() as scratch:
            config = example_config(workspace=scratch)
            config.transform["rules"] = [
                {"low": 0, "high": 250, "label": "small"},
                {"low": 200, "high": None, "label": "large"},
            ]
            with self.assertRaisesRegex(ValueError, "overlap"):
                GovernedPipeline(config)
            self.assertFalse(config.database_path.exists())


if __name__ == "__main__":
    unittest.main()
