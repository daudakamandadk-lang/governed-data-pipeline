"""Verify evidence units and missing/structural assessment semantics."""
from pathlib import Path
import sys
import unittest
import pandas as pd

from governed_data_pipeline.cleaning import CleaningEngine
from governed_data_pipeline.values import json_text
from governed_data_pipeline.quality_reports import table_evidence, validation_scorecard
from governed_data_pipeline.validation import validate_fields


class QualityReportTests(unittest.TestCase):
    def setUp(self):
        self.schema = {"primary_key": "id", "columns": {
            "id": {"dtype": "integer", "required": True},
            "amount": {"dtype": "float", "required": True, "min": 0},
            "note": {"dtype": "string", "required": False}}}

    def test_many_cell_failures_are_counted_as_distinct_rows(self):
        data = pd.DataFrame({"id": [1, 1, 3], "amount": [-1, None, 5]})
        report = validation_scorecard(data, self.schema, validate_fields(data, self.schema))
        self.assertEqual(report["reported_failed_rows"], 2)
        self.assertEqual(report["rows_without_reported_cell_issues"], 1)
        self.assertEqual(report["fields"]["id"]["issues_by_code"], {"duplicate_primary_key": 2})
        self.assertEqual(report["fields"]["note"]["assessment"], "not_present_optional")
        self.assertEqual(report["source_accuracy"], "not_assessed")

    def test_empty_missing_required_table_does_not_appear_certified(self):
        data = pd.DataFrame()
        report = validation_scorecard(data, self.schema, validate_fields(data, self.schema))
        self.assertFalse(report["contract_passed"])
        self.assertTrue(report["batch_failures"])
        self.assertEqual(report["fields"]["amount"]["assessment"], "required_column_missing")

    def test_before_after_evidence_preserves_the_original_and_serializes(self):
        data = pd.DataFrame({"id": [1], "amount": [" 10 "]})
        original = data.copy(deep=True)
        before = validate_fields(data, self.schema)
        cleaned = CleaningEngine().clean(data, self.schema)
        after = validate_fields(cleaned.data, self.schema)
        report = table_evidence(data, cleaned, self.schema, before, after)
        self.assertFalse(report["validation_before"]["contract_passed"])
        self.assertTrue(report["validation_after"]["contract_passed"])
        self.assertIn('"profile_after"', json_text(report))
        pd.testing.assert_frame_equal(data, original)
