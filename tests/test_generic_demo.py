"""Generic identity, compatibility and public database demonstration."""
from contextlib import redirect_stdout, closing
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from governed_data_pipeline.database_demo import demo_config, initialize_demo, main, mutate_demo
from governed_data_pipeline.database_pipeline import SqliteDatabasePipeline
from governed_data_pipeline.sqlite_cdc import SqliteChangeCapture


class GenericDemoTests(unittest.TestCase):
    def test_snapshot_five_events_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            config = demo_config(directory)
            self.assertTrue(initialize_demo(config))
            before = config.source_path.read_bytes()
            self.assertFalse(initialize_demo(config))
            self.assertEqual(config.source_path.read_bytes(), before)
            SqliteChangeCapture(config.source_path, config.schemas).install()
            pipeline = SqliteDatabasePipeline(config)
            first = pipeline.bootstrap()
            self.assertEqual(first.table_counts, {"customers": 2, "orders": 2})
            self.assertTrue(mutate_demo(config))
            self.assertFalse(mutate_demo(config))
            changed = pipeline.run_changes()
            self.assertEqual(changed.event_count, 5)
            self.assertEqual(changed.sequence, 5)
            self.assertEqual(changed.table_counts, {"customers": 2, "orders": 2})
            self.assertEqual(pipeline.run_changes().status, "no_changes")

    def test_invalid_custom_mutation_never_opens_the_source(self):
        with tempfile.TemporaryDirectory() as directory:
            config = demo_config(directory)
            path = Path(directory) / "job.json"
            settings = {"source_path": str(config.source_path), "database_path": str(config.database_path),
                        "schemas": config.schemas, "date_formats": config.date_formats}
            path.write_text(json.dumps(settings), encoding="utf-8")
            with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
                main(["--config", str(path), "--action", "mutate"])
            self.assertFalse(config.source_path.exists())

    def test_deprecated_cleaner_extends_primary_engine(self):
        from governed_data_pipeline import CleaningEngine, __version__
        from credit_risk_pipeline import CleaningEngine as old_engine
        from credit_risk_pipeline.cleaning import CleaningEngine as old_submodule_engine
        self.assertTrue(issubclass(old_engine, CleaningEngine))
        self.assertIs(old_engine, old_submodule_engine)
        self.assertEqual(__version__, "0.3.0")
        from governed_data_pipeline.demo import sample_transactions, example_config
        from credit_risk_pipeline.demo import sample_transactions as old_sample
        self.assertIn("customer_id", sample_transactions().columns)
        self.assertNotIn("applicant_id", sample_transactions().columns)
        self.assertIn("applicant_id", old_sample().columns)

    def test_primary_cleaner_requires_schema_and_legacy_default_still_works(self):
        from governed_data_pipeline import CleaningEngine
        from credit_risk_pipeline import CleaningEngine as old_engine
        data = pd.DataFrame({"applicant_id": [" AP00001 "]})
        with self.assertRaisesRegex(ValueError, "explicit schema"):
            CleaningEngine().clean(data)
        with self.assertRaisesRegex(ValueError, "applicant_id"):
            old_engine().clean(pd.DataFrame({"id": [" C1 "]}))
        legacy = old_engine().clean(data)
        schema = {"columns": {"applicant_id": {"dtype": "string"}}}
        explicit = CleaningEngine().clean(data, schema)
        pd.testing.assert_frame_equal(legacy.data, explicit.data)
        self.assertEqual(legacy.data.loc[0, "applicant_id"], "AP00001")
        self.assertEqual(legacy.corrections, explicit.corrections)
