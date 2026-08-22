from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wedo_movies_detector import BrandedBumperCut, extend_wedo_movies_program_hint_tails


class WedoMoviesTailTests(unittest.TestCase):
    @staticmethod
    def report() -> dict:
        return {
            "activation": {"matched": True},
            "duration_seconds": 1000.0,
            "candidates": [
                {
                    "start_seconds": 99.0,
                    "end_seconds": 218.0,
                    "duration_seconds": 119.0,
                    "last_layout_second": 215,
                }
            ],
        }

    @staticmethod
    def write_sidecar(path: Path, states: list[tuple[float, str]], reliability: str = "STRONG") -> None:
        records = [
            {
                "record_type": "metadata",
                "global_reliability": {"comskip": reliability},
            }
        ]
        records.extend(
            {
                "record_type": "observation",
                "time_seconds": second,
                "comskip_frame": int(second * 25),
                "comskip_local_state": state,
            }
            for second, state in states
        )
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_first_logo_return_ends_tail_without_post_detection_hold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / "fusion.jsonl"
            self.write_sidecar(
                sidecar,
                [
                    (215.0, "ABSENT"),
                    (251.96, "ABSENT"),
                    (252.0, "PRESENT"),
                    (252.04, "ABSENT"),
                ],
            )
            result = extend_wedo_movies_program_hint_tails(
                self.report(), sidecar_path=sidecar, max_tail_seconds=180.0
            )
            candidate = result["candidates"][0]
            self.assertEqual(candidate["end_seconds"], 252.0)
            self.assertEqual(candidate["program_hint_tail"]["reason"], "NORMAL_MOVIE_LOGO_RETURNED")
            self.assertEqual(result["tail_extension"]["post_detection_hold_seconds"], 0)

    def test_missing_logo_return_is_capped_at_exactly_three_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / "fusion.jsonl"
            self.write_sidecar(sidecar, [(215.0, "ABSENT"), (500.0, "ABSENT")])
            result = extend_wedo_movies_program_hint_tails(
                self.report(), sidecar_path=sidecar, max_tail_seconds=180.0
            )
            candidate = result["candidates"][0]
            self.assertEqual(candidate["end_seconds"], 396.0)
            self.assertEqual(candidate["program_hint_tail"]["reason"], "MAXIMUM_TAIL_REACHED")

    def test_unavailable_logo_sensor_never_causes_blind_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / "fusion.jsonl"
            self.write_sidecar(
                sidecar,
                [(215.0, "UNKNOWN")],
                reliability="REJECTED_BY_EXISTING_GATE",
            )
            result = extend_wedo_movies_program_hint_tails(
                self.report(), sidecar_path=sidecar, max_tail_seconds=180.0
            )
            candidate = result["candidates"][0]
            self.assertEqual(candidate["end_seconds"], 218.0)
            self.assertEqual(candidate["program_hint_tail"]["reason"], "LOGO_SENSOR_UNAVAILABLE")

    def test_confirmed_branded_bumper_cut_refines_late_logo_return(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / "fusion.jsonl"
            self.write_sidecar(sidecar, [(251.96, "ABSENT"), (252.0, "PRESENT")])
            cut = BrandedBumperCut(
                commercial_end_frame=6100,
                movie_start_frame=6101,
                scene_change_score=0.42,
                red_fraction=0.008,
                white_fraction=0.07,
                logo_mask_recall=0.94,
            )
            with patch("wedo_movies_detector._find_branded_bumper_cut", return_value=cut):
                result = extend_wedo_movies_program_hint_tails(
                    self.report(),
                    sidecar_path=sidecar,
                    max_tail_seconds=180.0,
                    video_path=Path(directory) / "movie.mp4",
                    fps=25.0,
                    logo_mask_path=Path(directory) / "selected.logo.txt",
                )
            candidate = result["candidates"][0]
            self.assertEqual(candidate["end_seconds"], 244.0)
            self.assertEqual(
                candidate["program_hint_tail"]["reason"],
                "BRANDED_WEDO_BUMPER_TO_MOVIE_CUT",
            )
            self.assertEqual(
                candidate["program_hint_tail"]["bumper_refinement"]["movie_start_frame"],
                6101,
            )

    def test_missing_branded_bumper_confirmation_preserves_logo_return(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / "fusion.jsonl"
            self.write_sidecar(sidecar, [(251.96, "ABSENT"), (252.0, "PRESENT")])
            with patch("wedo_movies_detector._find_branded_bumper_cut", return_value=None):
                result = extend_wedo_movies_program_hint_tails(
                    self.report(),
                    sidecar_path=sidecar,
                    video_path=Path(directory) / "movie.mp4",
                    fps=25.0,
                    logo_mask_path=Path(directory) / "selected.logo.txt",
                )
            candidate = result["candidates"][0]
            self.assertEqual(candidate["end_seconds"], 252.0)
            self.assertEqual(
                candidate["program_hint_tail"]["bumper_refinement"]["status"],
                "NO_UNAMBIGUOUS_BRANDED_BUMPER_CUT",
            )


if __name__ == "__main__":
    unittest.main()
