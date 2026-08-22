from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2

from wedo_movies_detector import (
    LayoutSample,
    WedoMoviesConfig,
    apply_wedo_movies_intervals,
    candidates_from_samples,
    is_wedo_movies_video,
    is_layout_present,
    layout_sample,
)


class WedoMoviesDetectorTests(unittest.TestCase):
    def test_filename_activation_is_exact_case_sensitive_substring(self) -> None:
        self.assertTrue(is_wedo_movies_video(Path("film_wedo-movies_hd.mp4")))
        self.assertFalse(is_wedo_movies_video(Path("film_WEDO-MOVIES_hd.mp4")))
        self.assertFalse(is_wedo_movies_video(Path("film_other-channel_hd.mp4")))

    def test_reference_promo_layout_is_present_but_program_and_ident_are_not(self) -> None:
        root = Path(__file__).resolve().parents[2] / "WeDoMovies Modul"
        config = WedoMoviesConfig()
        promo = cv2.resize(cv2.imread(str(root / "3.png")), (320, 180))
        program = cv2.resize(cv2.imread(str(root / "1.png")), (320, 180))
        ident = cv2.resize(cv2.imread(str(root / "2.png")), (320, 180))
        self.assertTrue(is_layout_present(layout_sample(promo, 0, config), config))
        self.assertFalse(is_layout_present(layout_sample(program, 0, config), config))
        self.assertFalse(is_layout_present(layout_sample(ident, 0, config), config))

    def test_four_red_segments_with_ident_gaps_form_one_candidate(self) -> None:
        config = WedoMoviesConfig()
        samples = []
        for start, end in ((100, 127), (130, 157), (160, 187), (190, 215)):
            samples.extend(
                LayoutSample(second, 0.92, 0.86, 0.16)
                for second in range(start, end + 1)
            )
        candidates = candidates_from_samples(samples, duration_seconds=1000, config=config)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].first_layout_second, 100)
        self.assertEqual(candidates[0].last_layout_second, 215)
        self.assertEqual(candidates[0].start_seconds, 99.0)
        self.assertEqual(candidates[0].end_seconds, 218.0)

    def test_short_red_scene_is_rejected(self) -> None:
        config = WedoMoviesConfig()
        samples = [LayoutSample(second, 0.95, 0.90, 0.0) for second in range(30, 42)]
        self.assertEqual(
            candidates_from_samples(samples, duration_seconds=1000, config=config),
            [],
        )

    def test_fusion_archives_original_and_updates_txt_and_edl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            txt = root / "final.txt"
            edl = root / "final.edl"
            txt.write_text(
                "FILE PROCESSING COMPLETE 10000 FRAMES AT  2500\n-------------------\n100\t200\n",
                encoding="ascii",
            )
            edl.write_text("4.000\t8.000\t0\n", encoding="ascii")
            report = {"candidates": [{"start_seconds": 10.0, "end_seconds": 20.0}]}
            result = apply_wedo_movies_intervals(
                txt_path=txt,
                edl_path=edl,
                report=report,
                fps=25.0,
            )
            self.assertEqual(result["fused_intervals"], [[100, 200], [250, 500]])
            self.assertIn("250\t500", txt.read_text(encoding="ascii"))
            self.assertIn("10.000\t20.000\t0", edl.read_text(encoding="ascii"))
            self.assertTrue((root / "final-pre-wedo.txt").is_file())
            self.assertTrue((root / "final-pre-wedo.edl").is_file())

    def test_fusion_rolls_back_both_outputs_if_second_publication_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            txt = root / "final.txt"
            edl = root / "final.edl"
            original_txt = "FILE PROCESSING COMPLETE 10000 FRAMES AT  2500\n-------------------\n100\t200\n"
            original_edl = "4.000\t8.000\t0\n"
            txt.write_text(original_txt, encoding="ascii")
            edl.write_text(original_edl, encoding="ascii")
            report = {"candidates": [{"start_seconds": 10.0, "end_seconds": 20.0}]}
            real_replace = __import__("os").replace

            def fail_txt_publication(source, target):
                if Path(target) == txt:
                    raise OSError("simulated publication failure")
                return real_replace(source, target)

            with mock.patch("wedo_movies_detector.os.replace", side_effect=fail_txt_publication):
                with self.assertRaisesRegex(OSError, "simulated publication failure"):
                    apply_wedo_movies_intervals(
                        txt_path=txt,
                        edl_path=edl,
                        report=report,
                        fps=25.0,
                    )

            self.assertEqual(txt.read_text(encoding="ascii"), original_txt)
            self.assertEqual(edl.read_text(encoding="ascii"), original_edl)
            self.assertFalse((root / "final.txt.wedo.tmp").exists())
            self.assertFalse((root / "final.edl.wedo.tmp").exists())


if __name__ == "__main__":
    unittest.main()
