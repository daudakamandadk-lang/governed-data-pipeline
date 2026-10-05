import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
import credit_risk_pipeline.incremental as incremental

class WatermarkTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / "watermarks.json"
        self.store = incremental.JsonWatermarkStore(self.path)
        self.store.save(incremental.WatermarkState("sample.csv", "transaction_id", 5))
        self.before = self.path.read_bytes()

    def assert_old_state_preserved(self):
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(self.store.load("sample.csv", "transaction_id").last_watermark, 5)
        self.assertEqual(set(self.path.parent.iterdir()), {self.path})

    def test_serialization_failure_preserves_previous_state(self):
        with self.assertRaises(TypeError):
            self.store.save(incremental.WatermarkState("sample.csv", "transaction_id", pd.Timestamp("2026-10-04")))
        self.assert_old_state_preserved()

    def test_nonfinite_watermark_is_rejected_without_state_loss(self):
        for value in (math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.save(incremental.WatermarkState("sample.csv", "transaction_id", value))
            self.assert_old_state_preserved()

    def test_flush_failure_preserves_state_and_cleans_temp_file(self):
        with patch.object(incremental.os, "fsync", side_effect=OSError("simulated flush failure")):
            with self.assertRaises(OSError):
                self.store.save(incremental.WatermarkState("sample.csv", "transaction_id", 6))
        self.assert_old_state_preserved()

    def test_replace_failure_preserves_state_and_cleans_temp_file(self):
        with patch.object(incremental.os, "replace", side_effect=OSError("simulated replacement failure")):
            with self.assertRaises(OSError):
                self.store.save(incremental.WatermarkState("sample.csv", "transaction_id", 6))
        self.assert_old_state_preserved()

    def test_successful_save_preserves_other_sources_and_unicode(self):
        self.store.save(incremental.WatermarkState("applicants-Ã©.csv", "id", 10))
        self.store.save(incremental.WatermarkState("sample.csv", "transaction_id", 6))
        self.assertEqual(self.store.load("sample.csv", "transaction_id").last_watermark, 6)
        self.assertEqual(self.store.load("applicants-Ã©.csv", "id").last_watermark, 10)
        self.assertEqual(set(self.path.parent.iterdir()), {self.path})

    def test_extraction_retries_until_explicit_commit(self):
        source = self.path.parent / "transactions.csv"
        source.write_text("transaction_id,amount\n1,20\n2,30\n", encoding="utf-8")
        engine = incremental.IncrementalFileExtractionEngine(self.store)
        first = engine.extract(source, "transaction_id")
        self.assertEqual(first.row_count, 2)
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(engine.extract(source, "transaction_id").row_count, 2)
        engine.commit(source, "transaction_id", first)
        self.assertEqual(engine.extract(source, "transaction_id").row_count, 0)

    def test_null_id_rejected_without_updating_state(self):
        source = self.path.parent / "sample.csv"
        source.write_text("transaction_id,amount\n6,20\n,30\n", encoding="utf-8")
        engine = incremental.IncrementalFileExtractionEngine(self.store)
        with self.assertRaisesRegex(ValueError, "missing values"):
            engine.extract(source, "transaction_id")
        self.assertEqual(self.path.read_bytes(), self.before)
