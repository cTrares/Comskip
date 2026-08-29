from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from commercial_macro_mode import (
    MacroSample,
    build_film_runs,
    intervals_from_film_runs,
    load_macro_channels,
    progressive_sample_stages,
    selected_macro_channel,
)


class CommercialMacroModeTests(unittest.TestCase):
    def test_progressive_grid_covers_whole_recording_before_refinement(self) -> None:
        stages = progressive_sample_stages(600.0, 20.0)
        self.assertEqual(0.0, stages[0][0])
        self.assertEqual(600.0, stages[0][-1])
        self.assertEqual(31, len({value for stage in stages for value in stage}))

    def test_long_film_runs_form_one_internal_break(self) -> None:
        samples = []
        for seconds in range(0, 3601, 20):
            present = seconds < 1200 or seconds >= 1800
            samples.append(MacroSample(float(seconds), 0.70 if present else 0.10, present))
        _runs, films = build_film_runs(samples, duration_seconds=3600.0)
        intervals = intervals_from_film_runs(films, duration_seconds=3600.0)
        self.assertEqual(1, len(intervals))
        self.assertLess(intervals[0][0], 1250.0)
        self.assertGreater(intervals[0][1], 1750.0)

    def test_channel_list_is_exact_and_editable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Makromodus-Sender.txt"
            config.write_text("# test\npro-7\nnitro\n", encoding="utf-8")
            channels = load_macro_channels(config)
            self.assertEqual("pro-7", selected_macro_channel(Path("Film_pro-7_hq.mp4"), channels))
            self.assertIsNone(selected_macro_channel(Path("Film_arte_hd.mp4"), channels))


if __name__ == "__main__":
    unittest.main()
