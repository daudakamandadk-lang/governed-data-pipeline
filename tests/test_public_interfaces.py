"""Public API compatibility and independent engine use."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy
import tempfile
import unittest
import pandas as pd

from credit_risk_pipeline.cleaning import CleaningEngine
from credit_risk_pipeline.dq import dimension_score, field, run_dq_checks
from credit_risk_pipeline.gates import GateStatus, can_continue, evaluate_gate
from credit_risk_pipeline.incremental import IncrementalFileExtractionEngine, JsonWatermarkStore
from credit_risk_pipeline.loading import IdempotentSqliteLoader
from credit_risk_pipeline.pipeline import stage_plan, stop_required
from credit_risk_pipeline.profiling import profile_data, profile_date
from credit_risk_pipeline.validation import validate_fields


class CompatibilityTests(unittest.TestCase):
    def test_empty_date_profile_keeps_original_none_sentinel(self):
        result = profile_date(pd.Series([], dtype="datetime64[ns]"))
        self.assertIsNone(result["earliest"])
        self.assertIsNone(result["latest"])

    def test_original_summary_and_warning_policy(self):
        data = pd.DataFrame({"id": [1, 2, 3], "amount": [10, -5, 8], "kind": ["A", "A", "B"]})
        checks = run_dq_checks(data, {"id": field(unique=True), "amount": field(min_value=0),
                                      "kind": field(allowed=["A", "B"])})
        score = dimension_score(checks["validity"])
        self.assertEqual(score, 2 / 3)
        gate = evaluate_gate(score, 1, .6)
        self.assertEqual(gate.status, GateStatus.WARN)
        self.assertTrue(can_continue(gate))
        self.assertFalse(can_continue(gate, allow_warning=False))
        self.assertFalse(stop_required(gate))
        self.assertTrue(stop_required(evaluate_gate(0, 1, .6)))

    def test_missing_columns_blanks_and_bad_numeric_values_report(self):
        data = pd.DataFrame({"amount": ["unknown", True, float("inf"), -1, None, 10],
                             "code": [" ", "", "A", "A", None, "B"]})
        result = run_dq_checks(data, {"id": field(unique=True), "amount": field(min_value=0),
                                     "code": field(unique=True)})
        self.assertFalse(result["completeness"]["id"]["passed"])
        self.assertEqual(result["completeness"]["code"]["missing"], 3)
        self.assertEqual(result["uniqueness"]["code"]["duplicates"], 1)
        self.assertEqual(result["validity"]["amount"]["invalid"], 4)

    def test_empty_missing_required_column_still_fails(self):
        result = run_dq_checks(pd.DataFrame(), {"id": field()})
        self.assertFalse(result["completeness"]["id"]["passed"])
        self.assertEqual(dimension_score({}), 1)

    def test_score_gate_rejects_boolean_nonfinite_and_text_settings(self):
        for value in (True, float("inf"), float("nan"), "0.8", None):
            with self.assertRaises(ValueError):
                evaluate_gate(value, 1, .6)
        with self.assertRaises(ValueError):
            evaluate_gate(.8, True, .6)

    def test_stage_order_returns_copy_and_load_precedes_reconciliation(self):
        stages = stage_plan()
        self.assertLess(stages.index("load"), stages.index("reconcile"))
        self.assertLess(stages.index("reconcile"), stages.index("commit"))
        stages.clear()
        self.assertIn("clean", stage_plan())

    def test_engines_work_without_an_orchestrator(self):
        schema = {"primary_key": "id", "columns": {"id": {"dtype": "integer", "required": True},
                                                    "amount": {"dtype": "float", "min": 0}}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.csv"
            pd.DataFrame({"id": [1, 2], "amount": [" 10 ", "20"]}).to_csv(source, index=False)
            extractor = IncrementalFileExtractionEngine(JsonWatermarkStore(root / "progress.json"))
            batch = extractor.extract(source, "id")
            self.assertFalse((root / "progress.json").exists())
            self.assertEqual(profile_data(batch.data)["rows"], 2)
            cleaned = CleaningEngine().clean(batch.data, schema)
            self.assertTrue(validate_fields(cleaned.data, schema).passed)
            loader = IdempotentSqliteLoader(root / "target.db")
            loaded = loader.load(cleaned.data, "transactions", schema)
            self.assertTrue(loader.reconcile(loaded, cleaned.data, schema, ["amount"]).passed)
            extractor.commit(source, "id", batch)
            self.assertEqual(extractor.extract(source, "id").row_count, 0)

    def test_original_example_still_runs(self):
        path = Path(__file__).resolve().parents[1] / "examples/dq_gate_demo.py"
        with redirect_stdout(io.StringIO()) as output:
            runpy.run_path(str(path), run_name="__main__")
        self.assertIn("Gate decision: WARN", output.getvalue())


if __name__ == "__main__":
    unittest.main()
