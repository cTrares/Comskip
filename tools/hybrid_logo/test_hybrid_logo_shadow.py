from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hybrid_logo_shadow import (
    ABSENT,
    NEUTRAL,
    PRESENT,
    Fractions,
    TimelineAggregator,
    TimelinePoint,
    block_evidence,
    parse_comskip_log,
    replace_logo_component,
)


class HybridLogoShadowTests(unittest.TestCase):
    def test_parse_final_comskip_block_table(self) -> None:
        text = """Threshold used - 1.0500\nBlock list after weighing\n---\n  7:--    2   2   0  22817  23581   912.64s   943.20s    30.56s   2.00  0.04\nend\n"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(text, encoding="utf-8")
            threshold, blocks = parse_comskip_log(path)
        self.assertEqual(threshold, 1.05)
        self.assertEqual(blocks[0].frame_start, 22817)
        self.assertEqual(blocks[0].normal_score, 2.0)

    def test_time_weighting_is_not_biased_by_dense_samples(self) -> None:
        points = [
            TimelinePoint(0.0, PRESENT, PRESENT),
            TimelinePoint(1.0, ABSENT, ABSENT),
            TimelinePoint(1.1, ABSENT, ABSENT),
            TimelinePoint(1.2, ABSENT, ABSENT),
            TimelinePoint(2.0, PRESENT, PRESENT),
        ]
        result = TimelineAggregator(points).fractions(0.0, 2.0)
        self.assertAlmostEqual(result.present, 0.5)
        self.assertAlmostEqual(result.absent, 0.5)

    def test_evidence_reuses_existing_threshold_conservatively(self) -> None:
        self.assertEqual(block_evidence(Fractions(0.26, 0.0, 0.74, 0.0, 1, 1), 0.25), PRESENT)
        self.assertEqual(block_evidence(Fractions(0.0, 0.76, 0.24, 0.0, 1, 1), 0.25), ABSENT)
        self.assertEqual(block_evidence(Fractions(0.0, 0.74, 0.26, 0.0, 1, 1), 0.25), NEUTRAL)

    def test_only_logo_component_is_replaced(self) -> None:
        self.assertAlmostEqual(replace_logo_component(2.0, 1.0, 0.01), 0.02)
        self.assertAlmostEqual(replace_logo_component(0.5, 0.01, 2.0), 100.0)


if __name__ == "__main__":
    unittest.main()
