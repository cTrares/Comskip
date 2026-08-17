from __future__ import annotations

import unittest

from hybrid_logo_fusion import (
    ABSENT,
    CONFLICT,
    PRESENT,
    UNKNOWN,
    ComskipAligner,
    ComskipObservation,
    RawLogoFinderPoint,
    classify_score,
    confirmed_changes,
    effective_stabilization_samples,
    fusion_state,
    stabilize,
)


class HybridLogoFusionTests(unittest.TestCase):
    def test_framewise_stabilization_preserves_phase2a_seconds(self) -> None:
        metadata = {
            "timeline": {
                "mode": "every_decodable_frame",
                "coarse_step_seconds": 1 / 25,
            }
        }
        self.assertEqual(
            effective_stabilization_samples(metadata, 3, 2),
            (75, 50, "phase2a_seconds_preserved"),
        )

    def test_hysteresis_band_is_unknown(self) -> None:
        self.assertEqual(classify_score(0.37, 0.38, 0.46), ABSENT)
        self.assertEqual(classify_score(0.42, 0.38, 0.46), UNKNOWN)
        self.assertEqual(classify_score(0.47, 0.38, 0.46), PRESENT)

    def test_persistence_rejects_single_sample_flip(self) -> None:
        changes = confirmed_changes([PRESENT, PRESENT, ABSENT, PRESENT, PRESENT], 2)
        self.assertEqual([(change.from_state, change.to_state) for change in changes], [(UNKNOWN, PRESENT)])

    def test_stabilization_refines_a_persistent_change(self) -> None:
        scores = [0.7] * 10 + [0.2] * 11
        points = [RawLogoFinderPoint(frame, frame / 10, score, "refine_frame") for frame, score in enumerate(scores)]
        points.extend(
            [
                RawLogoFinderPoint(0, 0.0, 0.7, "coarse"),
                RawLogoFinderPoint(5, 0.5, 0.7, "coarse"),
                RawLogoFinderPoint(10, 1.0, 0.2, "coarse"),
                RawLogoFinderPoint(20, 2.0, 0.2, "coarse"),
            ]
        )
        result = stabilize(
            sorted(points, key=lambda point: (point.frame, point.sample_kind)),
            absent_threshold=0.38,
            present_threshold=0.46,
            boundary_threshold=0.42,
            median_window=1,
            persistence_samples=2,
            frame_persistence=2,
        )
        self.assertEqual(result.state_changes[-1].to_state, ABSENT)
        self.assertEqual(result.state_changes[-1].frame, 10)
        self.assertEqual(result.state_changes[-1].precision, "frame_persistent")

    def test_framewise_timeline_is_a_stabilization_source(self) -> None:
        points = [
            RawLogoFinderPoint(frame, frame / 25.0, score, "frame")
            for frame, score in enumerate([0.7, 0.7, 0.7, 0.2, 0.2, 0.2])
        ]
        result = stabilize(
            points,
            absent_threshold=0.38,
            present_threshold=0.46,
            boundary_threshold=0.42,
            median_window=3,
            persistence_samples=2,
            frame_persistence=2,
        )
        self.assertEqual(result.state_changes[0].to_state, PRESENT)
        self.assertEqual(result.state_changes[-1].to_state, ABSENT)

    def test_pts_alignment_does_not_assume_equal_frame_ids(self) -> None:
        point = ComskipObservation(101, 4.0, 0.8, PRESENT, False, False, 0.1, False)
        aligned, delta = ComskipAligner([point], 0.1).nearest(4.02)
        self.assertEqual(aligned.frame, 101)
        self.assertAlmostEqual(delta, -0.02)

    def test_fusion_keeps_conflict_and_unknown_explicit(self) -> None:
        comskip = ComskipObservation(1, 0.0, 0.8, PRESENT, False, False, 0.1, False)
        self.assertEqual(fusion_state(ABSENT, True, comskip)[0], CONFLICT)
        self.assertEqual(fusion_state(PRESENT, False, comskip)[0], PRESENT)


if __name__ == "__main__":
    unittest.main()
