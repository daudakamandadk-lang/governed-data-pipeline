"""Behavioral checks with synthetic data only."""

import unittest

import numpy as np
import pandas as pd

from generic_analysis import AnalysisResult, analyze, infer_roles, route


class GenericAnalysisTests(unittest.TestCase):
    def test_roles_override_identifiers_and_codes(self):
        frame = pd.DataFrame({"id": [1, 2], "code": [0, 1], "flag": [True, False],
                              "time": pd.date_range("2026-01-01", periods=2)})
        result = analyze(frame, {"columns": {"id": {"role": "identifier"},
                                            "code": {"role": "category"}}})
        self.assertEqual(result.roles, {"id": "identifier", "code": "category",
                                        "flag": "category", "time": "time"})
        self.assertNotIn("id", result.descriptive)
        self.assertEqual(result.correlations, [])

    def test_statistics_exclusions_and_input_preservation(self):
        frame = pd.DataFrame({"x": [1., 2., 3., np.nan, np.inf]})
        original = frame.copy(deep=True)
        result = analyze(frame)
        self.assertEqual(result.descriptive["x"]["mean"], 2.)
        self.assertEqual(result.descriptive["x"]["variance"], 1.)
        self.assertEqual(result.descriptive["x"]["count"], 3)
        self.assertEqual(result.descriptive["x"]["missing"], 1)
        self.assertEqual(result.descriptive["x"]["non_finite"], 1)
        pd.testing.assert_frame_equal(frame, original)
        self.assertIn("review_quality_and_context", [s.action for s in result.next_steps])

    def test_pairwise_association_and_constant_exclusion(self):
        frame = pd.DataFrame({"x": [1., 2., 3., 4.], "y": [2., 4., 6., np.nan], "constant": [1.] * 4})
        result = analyze(frame)
        self.assertEqual(len(result.correlations), 1)
        self.assertEqual(result.correlations[0]["count"], 3)
        self.assertAlmostEqual(result.correlations[0]["coefficient"], 1.)
        self.assertTrue(result.distributions["constant"]["constant"])
        self.assertIsNone(result.distributions["constant"]["skew"])

    def test_groups_and_time_hooks(self):
        frame = pd.DataFrame({"group": ["A", "A", "B", None], "x": [1., 3., 7., 99.],
                              "time": pd.to_datetime(["2026-01-02", "2026-01-01", "2026-01-01", None])})
        result = analyze(frame, group_pairs=(("group", "x"),))
        self.assertEqual(result.groups[0]["summary"].loc["A", "mean"], 2.)
        self.assertEqual(result.groups[0]["excluded_missing_group"], 1)
        self.assertEqual(result.time_hooks[0]["duplicate_times"], 1)
        self.assertFalse(result.time_hooks[0]["monotonic"])
        self.assertIn("review_time_structure", [s.action for s in result.next_steps])

    def test_empty_nullable_and_small_samples(self):
        for values in [[], [None], [1], [1, 2]]:
            result = analyze(pd.DataFrame({"x": pd.Series(values, dtype="Float64")}))
            self.assertIsNone(result.distributions["x"]["skew"])
            self.assertEqual(result.correlations, [])

    def test_skew_router_and_thresholds(self):
        result = analyze(pd.DataFrame({"x": [1., 1., 1., 1., 100.]}))
        self.assertIn("inspect_distribution", [s.action for s in result.next_steps])
        self.assertNotIn("inspect_distribution", [s.action for s in route(result, skew_threshold=10)])
        with self.assertRaises(ValueError):
            route(AnalysisResult(0, {}), correlation_threshold=0)

    def test_invalid_metadata_and_group_pairs(self):
        frame = pd.DataFrame({"x": [1], "text": ["date"]})
        for columns in [{"missing": {"role": "measure"}}, {"x": {"role": "bad"}},
                        {"text": {"role": "time"}}, {"text": {"role": "measure"}}]:
            with self.assertRaises(ValueError):
                infer_roles(frame, {"columns": columns})
        with self.assertRaises(ValueError):
            analyze(frame, group_pairs=(("x", "text"),))
        with self.assertRaises(ValueError):
            infer_roles(pd.DataFrame([[1, 2]], columns=["x", "x"]))


if __name__ == "__main__":
    unittest.main()
