"""Generic public interfaces and database demonstration."""
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

    def test_primary_export_and_generic_sample_columns(self):
        from governed_data_pipeline import CleaningEngine, __version__
        from governed_data_pipeline.cleaning import CleaningEngine as submodule_engine
        from governed_data_pipeline.demo import sample_transactions
        self.assertIs(CleaningEngine, submodule_engine)
        self.assertEqual(__version__, "0.3.0")
        self.assertEqual(set(sample_transactions().columns),
                         {"transaction_id", "customer_id", "amount", "active", "order_date", "snapshot_date"})

    def test_primary_cleaner_requires_explicit_schema_and_preserves_evidence(self):
        from governed_data_pipeline import CleaningEngine
        data = pd.DataFrame({"customer_id": [" C00001 "]})
        snapshot = data.copy(deep=True)
        with self.assertRaisesRegex(ValueError, "explicit schema"):
            CleaningEngine().clean(data)
        schema = {"columns": {"customer_id": {"dtype": "string"}}}
        cleaned = CleaningEngine().clean(data, schema)
        pd.testing.assert_frame_equal(data, snapshot)
        self.assertEqual(cleaned.data.loc[0, "customer_id"], "C00001")
        self.assertEqual(cleaned.corrected_cells, 1)
        self.assertEqual(cleaned.corrections[0].original_value, " C00001 ")
