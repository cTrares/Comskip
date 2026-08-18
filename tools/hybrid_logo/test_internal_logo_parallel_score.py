from __future__ import annotations

import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from hybrid_logo_analysis import FrameScorer, ordered_bounded_map
from internal_logo_sensor import OverlayReference, ProgramOverlay, overlay_present_score_from_crop


class OrderedBoundedMapTests(unittest.TestCase):
    def test_out_of_order_completion_yields_original_order(self) -> None:
        def deliberately_reordered(value: int) -> int:
            time.sleep((7 - value) * 0.002)
            return value

        results = list(
            ordered_bounded_map(
                deliberately_reordered,
                range(8),
                max_workers=4,
                max_in_flight=8,
            )
        )
        self.assertEqual(results, list(range(8)))

    def test_short_input_and_partial_final_window(self) -> None:
        self.assertEqual(
            list(ordered_bounded_map(lambda value: value * 2, range(3), max_workers=8, max_in_flight=16)),
            [0, 2, 4],
        )
        self.assertEqual(
            list(ordered_bounded_map(lambda value: value, range(11), max_workers=4, max_in_flight=8)),
            list(range(11)),
        )

    def test_worker_exception_is_propagated(self) -> None:
        def fail_on_three(value: int) -> int:
            if value == 3:
                raise RuntimeError("expected worker failure")
            return value

        with self.assertRaisesRegex(RuntimeError, "expected worker failure"):
            list(ordered_bounded_map(fail_on_three, range(10), max_workers=2, max_in_flight=4))

    def test_in_flight_depth_is_bounded(self) -> None:
        depths: list[int] = []
        results = list(
            ordered_bounded_map(
                lambda value: value,
                range(25),
                max_workers=4,
                max_in_flight=8,
                depth_observer=depths.append,
            )
        )
        self.assertEqual(results, list(range(25)))
        self.assertEqual(max(depths), 8)


class ScoreDetailsTests(unittest.TestCase):
    def test_observation_does_not_change_released_score(self) -> None:
        crop = np.arange(16 * 12 * 3, dtype=np.uint8).reshape((12, 16, 3))
        gray = cv2.equalizeHist(cv2.GaussianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (3, 3), 0))
        edges = cv2.Canny(gray, 35, 110)
        mask = np.ones(gray.shape, dtype=np.uint8) * 255
        reference = OverlayReference(
            overlay=ProgramOverlay((0, 0, 16, 12), "test", 1.0, 1),
            gray=gray,
            edges=edges,
            edge_mask=mask,
            template_mask=mask,
        )
        expected = overlay_present_score_from_crop(reference, crop)
        details: dict[str, float] = {}
        observed = overlay_present_score_from_crop(reference, crop, details=details)
        self.assertEqual(observed, expected)
        self.assertEqual(details["score"], expected)
        self.assertIn("gray_score", details)
        self.assertIn("edge_score", details)

    def test_ffmpeg_failure_is_propagated(self) -> None:
        ffmpeg = Path(__file__).resolve().parents[2] / "dist" / "ComSkip" / "ffmpeg.exe"
        if not ffmpeg.is_file():
            self.skipTest("Portable FFmpeg is not available")
        gray = np.zeros((4, 4), dtype=np.uint8)
        mask = np.ones(gray.shape, dtype=np.uint8) * 255
        reference = OverlayReference(
            overlay=ProgramOverlay((0, 0, 4, 4), "test", 1.0, 1),
            gray=gray,
            edges=gray,
            edge_mask=mask,
            template_mask=mask,
        )
        scorer = FrameScorer(
            cv2,
            np,
            Path(__file__).with_name("missing-video.mp4"),
            reference,
            lambda _reference, _frame: 0.0,
            lambda _reference, _crop, _timings: 0.0,
        )
        with self.assertRaisesRegex(RuntimeError, "FFmpeg ROI decoder failed"):
            scorer.score_every_frame(3, fps=25.0, threshold=0.42, ffmpeg=ffmpeg, score_workers=4)


if __name__ == "__main__":
    unittest.main()
