from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from multiwindow_logo_experiment import (
    LEARNING_GUARD_SECONDS,
    LearningWindow,
    MaskCandidate,
    comskip_command,
    learning_windows,
    parse_mask,
    select_recurring_candidate,
)


class MultiwindowLogoExperimentTests(unittest.TestCase):
    def test_final_command_uses_inputs_without_experimental_switches(self) -> None:
        args = Namespace(comskip=Path("comskip.exe"), ini=Path("comskip.ini"))
        command = comskip_command(
            args,
            Path("film.mp4"),
            Path("out"),
            "film",
            logo=Path("selected.logo.txt"),
            sidecar=Path("internal.jsonl"),
            final=True,
        )
        self.assertIn("--logo", command)
        self.assertIn("--hybrid-logo-sidecar", command)
        self.assertNotIn("--multiwindow-logo-experimental", command)
        self.assertNotIn("--hybrid-logo-experimental", command)
        self.assertNotIn("--disable-excessive-length-penalty", command)

    def test_five_windows_respect_hard_guards_and_do_not_overlap(self) -> None:
        duration = 8590.0
        windows = learning_windows(duration)
        self.assertEqual(5, len(windows))
        self.assertGreaterEqual(windows[0].start_seconds, LEARNING_GUARD_SECONDS)
        self.assertLessEqual(windows[-1].end_seconds, duration - LEARNING_GUARD_SECONDS)
        self.assertTrue(all(left.end_seconds <= right.start_seconds for left, right in zip(windows, windows[1:])))

    def test_combined_mask_keeps_horizontal_and_vertical_edges_separate(self) -> None:
        payload = (
            "logoMinX=10\nlogoMaxX=11\nlogoMinY=20\nlogoMaxY=21\n"
            "picWidth=720\npicHeight=576\n\nCombined Logo Mask\n"
        ).encode("ascii") + b"\x82\n|+\n- \n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.logo.txt"
            path.write_bytes(payload)
            candidate = parse_mask(path, LearningWindow(1, 360, 480), (0.8, 0.9, 50))
        self.assertEqual({(10, 20), (11, 20)}, candidate.horizontal_edges)
        self.assertEqual({(11, 20), (10, 21)}, candidate.vertical_edges)

    def test_recurring_pair_beats_unrelated_first_candidate(self) -> None:
        def candidate(index: int, offset: int) -> MaskCandidate:
            edges = {(100 + offset + point, 50 + point) for point in range(8)}
            return MaskCandidate(
                window=LearningWindow(index, index * 100.0, index * 100.0 + 60),
                path=Path(f"window-{index}.logo.txt"),
                bbox=(95 + offset, 45, 115 + offset, 65),
                picture_size=(720, 576),
                horizontal_edges=set(edges),
                vertical_edges=set(edges),
                validation_quality=0.8,
                validation_present_fraction=0.8,
                validation_samples=50,
            )

        unrelated = candidate(1, -80)
        recurring_a = candidate(2, 0)
        recurring_b = candidate(4, 1)
        selected, _comparisons = select_recurring_candidate([unrelated, recurring_a, recurring_b])
        self.assertIsNotNone(selected)
        self.assertIn(selected.window.index, (2, 4))
        self.assertEqual(2, selected.support_count)


if __name__ == "__main__":
    unittest.main()
