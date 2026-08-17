from __future__ import annotations

import unittest

from hybrid_logo_analysis import (
    ComskipPoint,
    TimelinePoint,
    agreement,
    build_timeline,
    exact_transitions,
    frame_grid,
)


class HybridLogoAnalysisTests(unittest.TestCase):
    def test_frame_grid_includes_last_frame(self) -> None:
        self.assertEqual(frame_grid(101, 25.0, 1.0), [0, 25, 50, 75, 100])

    def test_transition_is_refined_to_adjacent_frames(self) -> None:
        def score(frame: int) -> float:
            return 0.8 if frame < 13 else 0.2

        points = build_timeline(
            total_frames=51,
            fps=25.0,
            sample_seconds=1.0,
            score_at=score,
            threshold=0.42,
            sharp_delta=0.12,
            subdivisions=5,
        )
        transitions = exact_transitions(points)
        self.assertIn(
            (12, 13),
            [(item["last_frame_before_change"], item["first_frame_after_change"]) for item in transitions],
        )

    def test_agreement_keeps_conflicts_explicit(self) -> None:
        comskip = ComskipPoint(0.8, True, False, False, 0.1, False)
        self.assertEqual(agreement(True, comskip), "agree_present")
        self.assertEqual(agreement(False, comskip), "conflict")
        self.assertIsNone(agreement(True, None))

    def test_exact_transitions_ignores_non_adjacent_samples(self) -> None:
        points = [
            TimelinePoint(10, 0.4, 0.8, True, "coarse"),
            TimelinePoint(20, 0.8, 0.2, False, "coarse"),
        ]
        self.assertEqual(exact_transitions(points), [])


if __name__ == "__main__":
    unittest.main()
