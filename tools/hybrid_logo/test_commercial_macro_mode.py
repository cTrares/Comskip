from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from commercial_macro_mode import (
    MacroSample,
    MacroRun,
    build_film_runs,
    guard_intervals_with_present_evidence,
    intervals_from_film_runs,
    load_macro_channels,
    progressive_sample_stages,
    repair_state_runs,
    semantic_return_review_markers,
    selected_macro_channel,
    _write_outputs,
    _refine_boundary,
)
from public_broadcaster_fast_mode import VideoMetadata


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

    def test_short_sensor_hole_is_repaired_before_minimum_duration(self) -> None:
        runs = [
            MacroRun(0.0, 920.0, True, 46, 0.62),
            MacroRun(920.0, 940.0, False, 1, 0.38),
            MacroRun(940.0, 1260.0, True, 16, 0.53),
            MacroRun(1260.0, 1460.0, False, 10, 0.35),
        ]
        repaired, bridges = repair_state_runs(runs)
        self.assertEqual(2, len(repaired))
        self.assertTrue(repaired[0].present)
        self.assertEqual(1260.0, repaired[0].end_seconds)
        self.assertEqual(1, len(bridges))

    def test_short_promo_chain_does_not_become_film_without_long_context(self) -> None:
        runs = [
            MacroRun(0.0, 300.0, False, 15, 0.34),
            MacroRun(300.0, 360.0, True, 3, 0.55),
            MacroRun(360.0, 420.0, False, 3, 0.36),
            MacroRun(420.0, 500.0, True, 4, 0.56),
            MacroRun(500.0, 800.0, False, 15, 0.35),
        ]
        repaired, bridges = repair_state_runs(runs)
        self.assertEqual(runs, repaired)
        self.assertEqual([], bridges)

    def test_stable_positive_evidence_splits_instead_of_being_cut(self) -> None:
        intervals, reviews = guard_intervals_with_present_evidence(
            [(1000.0, 1800.0)],
            [MacroRun(1320.0, 1500.0, True, 9, 0.56)],
            duration_seconds=5000.0,
        )
        self.assertEqual([(1000.0, 1320.0), (1500.0, 1800.0)], intervals)
        self.assertEqual("STABILER_POSITIVER_ABSCHNITT_IM_WERBEVORSCHLAG", reviews[0]["reason"])

    def test_short_remainder_becomes_review_instead_of_cut(self) -> None:
        intervals, reviews = guard_intervals_with_present_evidence(
            [(1000.0, 1300.0)],
            [MacroRun(1080.0, 1200.0, True, 6, 0.56)],
            duration_seconds=5000.0,
        )
        self.assertEqual([], intervals)
        self.assertEqual(3, len(reviews))

    def test_internal_return_has_bounded_review_corridor(self) -> None:
        reviews = semantic_return_review_markers(
            [(0.0, 300.0), (1000.0, 1500.0), (4900.0, 5000.0)],
            duration_seconds=5000.0,
        )
        self.assertEqual([420.0, 1620.0], [item["seconds"] for item in reviews])

    def test_review_marker_is_navigable_in_txt_but_never_cut_in_edl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = _write_outputs(
                film_root=root,
                metadata=VideoMetadata(1000.0, 25.0, 25000, 720, 576),
                channel="test",
                config_path=root / "Makromodus-Sender.txt",
                intervals_seconds=[(100.0, 200.0)],
                review_markers=[
                    {
                        "seconds": 320.0,
                        "reason": "LOGO_RUECKKEHR_KANN_EIGENWERBUNG_SEIN",
                        "range_seconds": [200.0, 320.0],
                    }
                ],
                details={},
                runtime_seconds=1.0,
            )
            txt = (root / "final" / "final.txt").read_text(encoding="ascii")
            edl = (root / "final" / "final.edl").read_text(encoding="ascii")
            self.assertIn("8001\t8001", txt)
            self.assertEqual(1, len(edl.splitlines()))
            self.assertEqual(1, len(result["review_markers"]))

    def test_local_median_recovers_noisy_visible_logo_return(self) -> None:
        observed = {
            3050.0: 0.350,
            3052.0: 0.478,
            3054.0: 0.332,
            3056.0: 0.433,
            3058.0: 0.388,
            3060.0: 0.402,
            3062.0: 0.563,
            3064.0: 0.651,
            3066.0: 0.599,
            3068.0: 0.363,
            3070.0: 0.483,
            3072.0: 0.400,
            3074.0: 0.363,
            3076.0: 0.384,
            3078.0: 0.435,
            3080.0: 0.403,
            3082.0: 0.506,
            3084.0: 0.616,
            3086.0: 0.433,
            3088.0: 0.642,
            3090.0: 0.623,
            3092.0: 0.352,
            3094.0: 0.608,
            3096.0: 0.448,
            3098.0: 0.591,
            3100.0: 0.406,
            3102.0: 0.589,
            3104.0: 0.387,
            3106.0: 0.369,
            3108.0: 0.397,
            3110.0: 0.400,
            3112.0: 0.380,
            3114.0: 0.596,
            3116.0: 0.456,
            3118.0: 0.439,
            3120.0: 0.430,
            3122.0: 0.455,
            3124.0: 0.448,
            3126.0: 0.447,
            3128.0: 0.611,
            3130.0: 0.512,
            3132.0: 0.522,
            3134.0: 0.626,
            3136.0: 0.515,
            3138.0: 0.682,
            3140.0: 0.696,
            3142.0: 0.387,
            3144.0: 0.386,
            3146.0: 0.617,
            3148.0: 0.391,
            3150.0: 0.528,
        }

        def score_at_times(times):
            return {seconds: observed[seconds] for seconds in times if seconds in observed}

        selected, detail = _refine_boundary(
            3110.0,
            target_present=True,
            duration_seconds=7000.0,
            score_at_times=score_at_times,
            deadline=10**12,
        )
        self.assertLessEqual(selected, 3082.0)
        self.assertEqual("REFINED", detail["status"])

    def test_channel_list_is_exact_and_editable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Makromodus-Sender.txt"
            config.write_text("# test\npro-7\nnitro\n", encoding="utf-8")
            channels = load_macro_channels(config)
            self.assertEqual("pro-7", selected_macro_channel(Path("Film_pro-7_hq.mp4"), channels))
            self.assertIsNone(selected_macro_channel(Path("Film_arte_hd.mp4"), channels))


if __name__ == "__main__":
    unittest.main()
