from __future__ import annotations

import unittest

from hybrid_logo_evaluate import changed_ranges, truth_metrics


class HybridLogoEvaluateTests(unittest.TestCase):
    def test_truth_metrics_are_frame_inclusive(self) -> None:
        truth = {"ads": [(10, 19)], "show": [(30, 39)]}
        metrics = truth_metrics(truth, [(15, 34)])
        self.assertEqual(metrics["ground_truth_ad_frames"], 10)
        self.assertEqual(metrics["correct_ad_frames"], 5)
        self.assertEqual(metrics["missed_ad_frames"], 5)
        self.assertEqual(metrics["false_positive_show_frames"], 5)

    def test_changed_ranges_compare_final_frame_classes(self) -> None:
        changes = changed_ranges([(10, 19)], [(15, 24)], 30)
        self.assertEqual(changes, [(10, 14, "COMMERCIAL", "SHOW"), (20, 24, "SHOW", "COMMERCIAL")])


if __name__ == "__main__":
    unittest.main()
