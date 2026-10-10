"""Behavior and failure-boundary coverage for the connected CSV workflow."""

from contextlib import closing, redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from governed_data_pipeline.cleaning import CleaningEngine
from governed_data_pipeline.pipeline import GovernedPipeline, PipelineConfig
from governed_data_pipeline.loading import IdempotentSqliteLoader, ReplayConflict
from governed_data_pipeline.values import json_text
from governed_data_pipeline.record_gates import GateThresholds, evaluate_gate
from governed_data_pipeline.demo import example_config, main, sample_transactions
from governed_data_pipeline.validation import validate_fields, validate_schema


def table_schema(columns):
    return {"primary_key": "id", "columns": {"id": {"dtype": "integer", "required": True, "unique": True}, **columns}}


class FieldRuleTests(unittest.TestCase):
    def test_boolean_tokens_are_explicit_and_numbers_do_not_become_booleans(self):
        schema = table_schema({"flag": {"dtype": "boolean", "required": True}})
        original = pd.DataFrame({"id": range(1, 7), "flag": [" TRUE ", "false", 1, "yes", None, np.bool_(True)]})
        snapshot = original.copy(deep=True)
        cleaned = CleaningEngine().clean(original, schema)
        pd.testing.assert_frame_equal(original, snapshot)
        self.assertEqual(cleaned.data.flag.iloc[:2].tolist(), [True, False])
        self.assertEqual([issue.row_position for issue in cleaned.issues], [2, 3])
        result = validate_fields(cleaned.data, schema)
        self.assertEqual([issue.row_position for issue in result.issues], [2, 3, 4])

    def test_configured_boolean_alias_and_unknown_token(self):
        schema = table_schema({"flag": {"dtype": "boolean", "boolean_tokens": {"yes": True, "no": False}}})
        result = CleaningEngine().clean(pd.DataFrame({"id": [1, 2], "flag": ["YES", "maybe"]}), schema)
        self.assertIs(result.data.flag.iloc[0], True)
        self.assertEqual(result.data.flag.iloc[1], "maybe")
        self.assertEqual(result.issues[0].code, "boolean_parse_failed")

    def test_numeric_infinity_fractional_integer_and_boolean_are_invalid(self):
        schema = table_schema({"amount": {"dtype": "float"}, "count": {"dtype": "integer"}})
        frame = pd.DataFrame({"id": [1, 2, 3], "amount": ["inf", np.bool_(True), "unknown"], "count": ["1.5", "2", True]})
        result = CleaningEngine().clean(frame, schema)
        self.assertEqual(result.data.amount.iloc[0], "inf")
        self.assertEqual(result.data["count"].iloc[1], 2)
        self.assertEqual(len(result.issues), 5)
        self.assertFalse(validate_fields(result.data, schema).passed)

    def test_required_optional_types_and_other_unique_fields(self):
        schema = table_schema({"code": {"dtype": "string", "unique": True}, "amount": {"dtype": "float", "required": False}})
        result = validate_fields(pd.DataFrame({"id": [1, 2], "code": ["same", "same"], "amount": [None, 5]}), schema)
        self.assertEqual([issue.code for issue in result.issues], ["duplicate_value", "duplicate_value"])
        self.assertTrue(validate_fields(pd.DataFrame({"id": [1], "code": ["one"]}), schema).passed)
        wrong = validate_fields(pd.DataFrame({"id": [1], "code": [7]}), schema)
        self.assertEqual(wrong.issues[0].code, "type_mismatch")

    def test_temporal_and_numeric_cross_field_comparisons(self):
        schema = table_schema({"start": {"dtype": "date"}, "end": {"dtype": "date"},
                               "net": {"dtype": "float"}, "gross": {"dtype": "float"}})
        schema["comparisons"] = [
            {"left": "start", "right": "end", "operator": "le", "code": "date_order"},
            {"left": "net", "right": "gross", "operator": "le", "code": "net_exceeds_gross"}]
        frame = pd.DataFrame({"id": [1], "start": ["2026-10-05"], "end": ["2026-10-01"], "net": [200], "gross": [100]})
        result = validate_fields(frame, schema)
        self.assertEqual({issue.code for issue in result.issues}, {"date_order", "net_exceeds_gross"})

    def test_conditional_consistency_and_null_comparisons(self):
        schema = table_schema({"status": {"dtype": "category"}, "tenure": {"dtype": "integer"}})
        schema["comparisons"] = [{"left": "tenure", "operator": "eq", "value": 0,
                                   "when": {"column": "status", "equals": "Inactive"}, "code": "inactive_tenure"}]
        frame = pd.DataFrame({"id": [1, 2, 3], "status": ["Inactive", "Active", "Inactive"], "tenure": [5, 10, None]})
        result = validate_fields(frame, schema)
        self.assertEqual([issue.row_position for issue in result.issues], [0])

    def test_reference_presence_and_missing_reference_data(self):
        schema = table_schema({"customer_id": {"dtype": "string", "foreign_key": "customers.customer_id"}})
        frame = pd.DataFrame({"id": [1, 2], "customer_id": ["A1", "A2"]})
        self.assertEqual(validate_fields(frame, schema).batch_failures, ["reference_unavailable:customers.customer_id"])
        references = {"customers": pd.DataFrame({"customer_id": ["A1"]})}
        result = validate_fields(frame, schema, references)
        self.assertEqual([(issue.row_position, issue.code) for issue in result.issues], [(1, "foreign_key_not_found")])

    def test_invalid_contracts_and_gate_settings_fail_before_loading(self):
        for schema in ({"columns": {}}, table_schema({"wrong": {"dtype": "mystery"}})):
            with self.assertRaises(ValueError):
                validate_schema(schema)
        for thresholds in (GateThresholds(max_reject_rate=None), GateThresholds(max_quarantine_rate=True),
                           GateThresholds(max_quarantine_rate=0.2, warn_quarantine_rate=0.5)):
            with self.assertRaises(ValueError):
                evaluate_gate([], thresholds)

    def test_unknown_columns_and_nonunique_reference_keys_stop_a_batch(self):
        schema = table_schema({"code": {"dtype": "string", "foreign_key": "codes.id"}})
        frame = pd.DataFrame({"id": [1], "code": ["A1"], "extra": ["uncontracted"]})
        result = validate_fields(frame, schema, {"codes": pd.DataFrame({"id": ["A1", "A1"]})})
        self.assertEqual(result.batch_failures, ["unexpected_column:extra", "reference_keys_not_unique:codes.id"])

    def test_optional_unique_field_ignores_missing_and_blank_values(self):
        schema = table_schema({"code": {"dtype": "string", "unique": True}})
        frame = pd.DataFrame({"id": [1, 2, 3, 4], "code": ["", "", None, None]})
        self.assertTrue(validate_fields(frame, schema).passed)

    def test_malformed_rule_metadata_is_rejected(self):
        for rules in ({"dtype": "float", "min": True}, {"dtype": "float", "max": float("inf")},
                      {"dtype": "boolean", "boolean_tokens": {"YES": True}},
                      {"dtype": "string", "foreign_key": "invalid-reference"}):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                validate_schema(table_schema({"field": rules}))


class GovernedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.config = example_config(workspace=self.scratch.name)
        self.config.source.parent.mkdir(parents=True)
        sample_transactions().to_csv(self.config.source, index=False)

    def query(self, sql, params=()):
        with closing(sqlite3.connect(self.config.database_path)) as connection:
            return connection.execute(sql, params).fetchall()

    def test_clean_run_loads_reconciles_commits_and_logs_every_stage(self):
        result = GovernedPipeline(self.config).run()
        self.assertEqual((result.status, result.extracted, result.inserted), ("succeeded", 6, 6))
        self.assertEqual(result.candidate_watermark, 6)
        self.assertEqual(self.query("SELECT COUNT(*) FROM transactions")[0][0], 6)
        self.assertEqual(self.query("SELECT status FROM etl_runs")[0][0], "succeeded")
        stages = [row[0] for row in self.query("SELECT stage FROM etl_events WHERE status='started' ORDER BY event_id")]
        self.assertLess(stages.index("persist_audit"), stages.index("load"))
        self.assertLess(stages.index("reconcile"), stages.index("commit"))
        self.assertGreater(self.query("SELECT COUNT(*) FROM etl_corrections")[0][0], 0)
        self.assertTrue(json.loads(self.query("SELECT policy FROM etl_runs")[0][0])["schema"])
        self.assertEqual(GovernedPipeline(self.config).run().status, "no_new_rows")

    def test_strict_stop_preserves_progress_and_persists_three_bad_rows(self):
        sample_transactions(True).to_csv(self.config.source, index=False)
        result = GovernedPipeline(self.config).run()
        self.assertEqual((result.status, result.quarantined, result.accepted), ("stopped", 3, 3))
        self.assertFalse(self.config.watermark_path.exists())
        self.assertEqual(self.query("SELECT COUNT(*) FROM etl_quarantine")[0][0], 3)
        self.assertFalse(self.query("SELECT name FROM sqlite_master WHERE name='transactions'"))
        GovernedPipeline(self.config).run()
        self.assertEqual(self.query("SELECT COUNT(*) FROM etl_quarantine")[0][0], 3)

    def test_lenient_gate_requires_durable_quarantine_before_advancing(self):
        sample_transactions(True).to_csv(self.config.source, index=False)
        self.config.gate = GateThresholds(max_quarantine_rate=0.6, warn_quarantine_rate=0)
        result = GovernedPipeline(self.config).run()
        self.assertEqual((result.status, result.gate_outcome, result.inserted), ("succeeded", "warn", 3))
        self.assertEqual(self.query("SELECT transaction_id FROM transactions ORDER BY transaction_id"), [(1,), (2,), (6,)])
        self.assertEqual(self.query("SELECT COUNT(*) FROM etl_quarantine")[0][0], 3)
        self.assertEqual(GovernedPipeline(self.config).run().candidate_watermark, 6)

    def test_missing_column_stops_even_for_empty_input(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                data = sample_transactions().drop(columns="active")
                if empty:
                    data = data.iloc[:0]
                data.to_csv(self.config.source, index=False)
                result = GovernedPipeline(self.config).run()
                self.assertEqual(result.status, "stopped")
                self.assertFalse(self.config.watermark_path.exists())

    def test_failed_quarantine_write_blocks_loading(self):
        sample_transactions(True).to_csv(self.config.source, index=False)
        self.config.max_attempts = 1
        pipeline = GovernedPipeline(self.config)
        with patch.object(pipeline.journal, "persist", side_effect=OSError("audit disk failed")):
            with self.assertRaises(OSError):
                pipeline.run()
        self.assertFalse(self.config.watermark_path.exists())
        self.assertFalse(self.query("SELECT name FROM sqlite_master WHERE name='transactions'"))
        self.assertEqual(self.query("SELECT status FROM etl_runs"), [("failed",)])

    def test_failed_load_blocks_commit_and_records_error(self):
        pipeline = GovernedPipeline(self.config)
        with patch.object(pipeline.loader, "load", side_effect=ValueError("load failed")):
            with self.assertRaisesRegex(ValueError, "load failed"):
                pipeline.run()
        self.assertFalse(self.config.watermark_path.exists())
        self.assertIn("load failed", self.query("SELECT error FROM etl_runs")[0][0])

    def test_commit_failure_retries_identical_rows_without_duplication(self):
        pipeline = GovernedPipeline(self.config)
        commit = pipeline.extractor.commit
        attempts = []

        def fail_once(*args):
            attempts.append(1)
            if len(attempts) == 1:
                raise OSError("temporary progress failure")
            return commit(*args)

        with patch.object(pipeline.extractor, "commit", side_effect=fail_once):
            result = pipeline.run()
        self.assertEqual((result.status, result.inserted, result.reused), ("succeeded", 0, 6))
        self.assertEqual(self.query("SELECT COUNT(*) FROM transactions")[0][0], 6)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.query("SELECT COUNT(*) FROM etl_events WHERE stage='retry'")[0][0], 1)

    def test_failed_commit_can_be_recovered_by_a_new_run(self):
        self.config.max_attempts = 1
        pipeline = GovernedPipeline(self.config)
        with patch.object(pipeline.extractor, "commit", side_effect=OSError("progress unavailable")):
            with self.assertRaises(OSError):
                pipeline.run()
        self.assertFalse(self.config.watermark_path.exists())
        result = GovernedPipeline(self.config).run()
        self.assertEqual((result.inserted, result.reused), (0, 6))
        self.assertEqual(self.query("SELECT COUNT(*) FROM transactions")[0][0], 6)

    def test_existing_key_with_changed_values_rolls_back_new_inserts(self):
        GovernedPipeline(self.config).run()
        data = CleaningEngine().clean(sample_transactions(), self.config.schema, self.config.date_formats).data
        batch = data.iloc[[0, 1]].copy()
        batch.iloc[0, batch.columns.get_loc("transaction_id")] = 7
        batch.iloc[1, batch.columns.get_loc("amount")] = 999
        loader = IdempotentSqliteLoader(self.config.database_path)
        # Include the existing target's derived column to keep the schema stable.
        from governed_data_pipeline.transformation import BandTransformer, BandRule
        batch = BandTransformer("amount", "amount_band", [BandRule(0, 250, "small"), BandRule(250, None, "large")]).transform(batch)
        with self.assertRaises(ReplayConflict):
            loader.load(batch, self.config.target_table, self.config.schema)
        self.assertEqual(self.query("SELECT COUNT(*) FROM transactions")[0][0], 6)
        self.assertFalse(self.query("SELECT transaction_id FROM transactions WHERE transaction_id=7"))

    def test_value_tampering_fails_reconciliation_with_unchanged_counts(self):
        pipeline = GovernedPipeline(self.config)
        original_reconcile = pipeline.loader.reconcile

        def tamper_then_reconcile(*args):
            with closing(sqlite3.connect(self.config.database_path)) as connection:
                with connection:
                    connection.execute("UPDATE transactions SET amount=999 WHERE transaction_id=1")
            return original_reconcile(*args)

        with patch.object(pipeline.loader, "reconcile", side_effect=tamper_then_reconcile):
            with self.assertRaisesRegex(RuntimeError, "Reconciliation"):
                pipeline.run()
        self.assertFalse(self.config.watermark_path.exists())
        checks = json.loads(self.query("SELECT details FROM etl_events WHERE stage='reconcile' AND status='checks'")[0][0])["checks"]
        self.assertTrue(any(check["name"] == "batch_values_digest" and not check["passed"] for check in checks))
        self.assertTrue(any(check["name"] == "total:amount" and not check["passed"] for check in checks))

    def test_source_change_before_commit_withholds_progress(self):
        pipeline = GovernedPipeline(self.config)
        original_load = pipeline.loader.load

        def change_source(*args):
            result = original_load(*args)
            self.config.source.write_text(self.config.source.read_text() + "7,A007,100,true,2026-10-01,2026-10-05\n")
            return result

        with patch.object(pipeline.loader, "load", side_effect=change_source):
            with self.assertRaisesRegex(RuntimeError, "Source changed"):
                pipeline.run()
        self.assertFalse(self.config.watermark_path.exists())

    def test_persisted_quarantine_corruption_blocks_commit(self):
        sample_transactions(True).to_csv(self.config.source, index=False)
        self.config.gate = GateThresholds(max_quarantine_rate=0.6)
        pipeline = GovernedPipeline(self.config)
        with patch.object(pipeline.journal, "verify_quarantine", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Reconciliation"):
                pipeline.run()
        self.assertFalse(self.config.watermark_path.exists())

    def test_path_aliases_and_job_identity_changes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            GovernedPipeline(replace(self.config, watermark_path=self.config.source))
        GovernedPipeline(self.config).run()
        other = self.config.source.with_name("other.csv")
        sample_transactions().to_csv(other, index=False)
        with self.assertRaisesRegex(ValueError, "identity"):
            GovernedPipeline(replace(self.config, source=other)).run()

    def test_cli_preserves_samples_and_reports_a_repeat_as_no_new_rows(self):
        previous = Path.cwd()
        import os
        try:
            os.chdir(self.scratch.name)
            initial = self.config.source.read_bytes()
            with redirect_stdout(io.StringIO()):
                first = main([])
                second = main([])
            self.assertEqual((first.status, second.status), ("succeeded", "no_new_rows"))
            self.assertEqual(self.config.source.read_bytes(), initial)
        finally:
            os.chdir(previous)

    def test_audit_retains_blank_original_text(self):
        self.assertEqual(json.loads(json_text({"id": "   "}))["id"], "   ")

    def test_string_identifiers_keep_leading_zeroes_and_na_text(self):
        data = sample_transactions()
        data["customer_id"] = ["001", "002", "003", "004", "005", "NA"]
        data.to_csv(self.config.source, index=False)
        result = GovernedPipeline(self.config).run()
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(self.query("SELECT customer_id FROM transactions ORDER BY transaction_id"),
                         [("001",), ("002",), ("003",), ("004",), ("005",), ("NA",)])

    def test_transformation_cannot_overwrite_an_existing_field(self):
        self.config.transform["derived_column"] = "customer_id"
        with self.assertRaisesRegex(ValueError, "overwrite"):
            GovernedPipeline(self.config).run()
        self.assertFalse(self.config.watermark_path.exists())

    def test_unavailable_reference_blocks_loading(self):
        self.config.schema["columns"]["customer_id"]["foreign_key"] = "customers.customer_id"
        result = GovernedPipeline(self.config).run()
        self.assertEqual(result.status, "stopped")
        self.assertFalse(self.config.watermark_path.exists())

    def test_reference_identifiers_and_fingerprints_are_preserved(self):
        frame = sample_transactions()
        frame["customer_id"] = ["001", "002", "003", "004", "005", "006"]
        frame.to_csv(self.config.source, index=False)
        reference = self.config.source.with_name("customers.csv")
        frame[["customer_id"]].to_csv(reference, index=False)
        self.config.reference_paths = {"customers": reference}
        self.config.schema["columns"]["customer_id"]["foreign_key"] = "customers.customer_id"
        self.assertEqual(GovernedPipeline(self.config).run().status, "succeeded")
        lineage = json.loads(self.query("SELECT details FROM etl_events WHERE stage='lineage'")[0][0])
        self.assertEqual(len(lineage["references"]["customers"]), 64)

    def test_reference_change_after_loading_holds_progress(self):
        reference = self.config.source.with_name("customers.csv")
        pd.DataFrame({"customer_id": [f"A00{number}" for number in range(1, 7)]}).to_csv(reference, index=False)
        self.config.reference_paths = {"customers": reference}
        self.config.schema["columns"]["customer_id"]["foreign_key"] = "customers.customer_id"
        pipeline = GovernedPipeline(self.config)
        load = pipeline.loader.load

        def change_reference(*args):
            result = load(*args)
            reference.write_text(reference.read_text() + "A007\n")
            return result

        with patch.object(pipeline.loader, "load", side_effect=change_reference):
            with self.assertRaisesRegex(RuntimeError, "Reference changed"):
                pipeline.run()
        self.assertFalse(self.config.watermark_path.exists())

    def test_dirty_cli_stops_then_explicit_policy_loads_only_accepted_rows(self):
        previous = Path.cwd()
        import os
        try:
            os.chdir(self.scratch.name)
            with redirect_stdout(io.StringIO()):
                stopped = main(["--scenario", "dirty"])
                allowed = main(["--scenario", "dirty", "--allow-quarantine"])
                repeated = main(["--scenario", "dirty", "--allow-quarantine"])
            self.assertEqual((stopped.status, allowed.status, repeated.status),
                             ("stopped", "succeeded", "no_new_rows"))
            self.assertEqual((allowed.accepted, allowed.quarantined, allowed.inserted), (3, 3, 3))
        finally:
            os.chdir(previous)

    def test_invalid_target_and_totals_fail_before_audit_database_creation(self):
        for config in (replace(self.config, target_table="etl_runs"), replace(self.config, sum_columns=["active"])):
            with self.subTest(config=config), self.assertRaises(ValueError):
                GovernedPipeline(config)
        self.assertFalse(self.config.database_path.exists())


if __name__ == "__main__":
    unittest.main()
