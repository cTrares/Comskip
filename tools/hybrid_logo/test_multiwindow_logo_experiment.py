from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from multiwindow_logo_experiment import (
    LEARNING_DIRECTORY_NAME,
    LEARNING_GUARD_SECONDS,
    LearningWindow,
    MaskCandidate,
    comskip_command,
    framearray_rescore_command,
    learning_window_artifacts,
    learning_windows,
    parse_mask,
    select_recurring_candidate,
    validate_csv_rescore_log,
    validate_framearray,
)


class MultiwindowLogoExperimentTests(unittest.TestCase):
    def test_learning_artifact_paths_are_short_and_film_name_independent(self) -> None:
        runtime = Path(tempfile.gettempdir()) / "ComskipFinal" / "r" / "a7f31c92d4" / "run"
        artifacts = learning_window_artifacts(runtime, 5)
        self.assertEqual(artifacts.root, runtime / LEARNING_DIRECTORY_NAME / "w5")
        self.assertEqual(artifacts.clip.name, "w5.mp4")
        self.assertEqual(artifacts.mask.name, "w5.logo.txt")
        self.assertEqual(artifacts.raw.name, "w5.logo-raw.csv")
        for original_stem in (
            "film",
            "Film mit Leerzeichen",
            "Übermäßig-langer-Filmname-" + "x" * 160,
            "Extrem-" + "y" * 230,
        ):
            self.assertNotIn(original_stem, str(artifacts.root))

    def test_sensor_command_requests_full_framearray(self) -> None:
        args = Namespace(comskip=Path("comskip.exe"), ini=Path("comskip.ini"))
        command = comskip_command(
            args,
            Path("film.mp4"),
            Path("sensor"),
            "film",
            logo=Path("selected.logo.txt"),
            raw=True,
            framearray=True,
        )
        self.assertIn("--logo-raw", command)
        self.assertIn("--csvout", command)
        self.assertEqual(Path(command[-1]), Path("film.mp4"))

    def test_final_command_uses_framearray_and_sidecar_without_video_fallback(self) -> None:
        args = Namespace(comskip=Path("comskip.exe"), ini=Path("comskip.ini"))
        command = framearray_rescore_command(
            args,
            Path("sensor/film.csv"),
            Path("out"),
            "film",
            logo=Path("selected.logo.txt"),
            sidecar=Path("internal.jsonl"),
        )
        self.assertIn("--logo", command)
        self.assertIn("--hybrid-logo-sidecar", command)
        self.assertEqual(Path(command[-1]), Path("sensor/film.csv"))
        self.assertNotIn("film.mp4", command)
        self.assertNotIn("--multiwindow-logo-experimental", command)
        self.assertNotIn("--hybrid-logo-experimental", command)
        self.assertNotIn("--disable-excessive-length-penalty", command)

    def test_final_command_rejects_non_csv_input(self) -> None:
        args = Namespace(comskip=Path("comskip.exe"), ini=Path("comskip.ini"))
        with self.assertRaisesRegex(ValueError, "requires a framearray CSV"):
            framearray_rescore_command(
                args,
                Path("film.mp4"),
                Path("out"),
                "film",
                logo=Path("selected.logo.txt"),
                sidecar=Path("internal.jsonl"),
            )

    def test_framearray_validation_accepts_complete_contiguous_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completion = root / "film.txt"
            completion.write_text("FILE PROCESSING COMPLETE 3 FRAMES AT 2500\n", encoding="utf-8")
            framearray = root / "film.csv"
            framearray.write_text(
                "sep=,\n"
                "frame,brightness,scene_change,logo,uniform,sound,minY,MaxY,ar_ratio,goodEdge,"
                "isblack,cutscene, MinX, MaxX, hasBright, Dimcount,PTS,25.0\n"
                "1,1,1,0,1,1,1,1,1.0,0.0,0,0,1,1,1,1,0.0,0,2\n"
                "2,1,1,0,1,1,1,1,1.0,0.0,0,0,1,1,1,1,0.04,0,2\n"
                "3,1,1,0,1,1,1,1,1.0,0.0,0,0,1,1,1,1,0.08,0,2\n",
                encoding="utf-8",
            )
            result = validate_framearray(framearray, completion, 3)
            self.assertEqual(result["frames"], 3)
            self.assertGreater(result["bytes"], 0)
            with self.assertRaisesRegex(RuntimeError, "is stale"):
                validate_framearray(
                    framearray,
                    completion,
                    3,
                    minimum_mtime_ns=framearray.stat().st_mtime_ns + 1,
                )

    def test_framearray_validation_rejects_missing_empty_and_incomplete_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completion = root / "film.txt"
            completion.write_text("FILE PROCESSING COMPLETE 2 FRAMES AT 2500\n", encoding="utf-8")
            framearray = root / "film.csv"
            with self.assertRaisesRegex(RuntimeError, "is missing"):
                validate_framearray(framearray, completion, 2)
            framearray.write_bytes(b"")
            with self.assertRaisesRegex(RuntimeError, "is empty"):
                validate_framearray(framearray, completion, 2)
            framearray.write_text(
                "sep=,\n"
                "frame,brightness,scene_change,logo,uniform,sound,minY,MaxY,ar_ratio,goodEdge,"
                "isblack,cutscene, MinX, MaxX, hasBright, Dimcount,PTS,25.0\n"
                "1,1,1,0,1,1,1,1,1.0,0.0,0,0,1,1,1,1,0.0,0,2\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "is incomplete"):
                validate_framearray(framearray, completion, 2)

    def test_csv_rescore_log_requires_process_csv_and_no_decode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            command_log = Path(directory) / "command.log"
            comskip_log = Path(directory) / "film.log"
            command_log.write_text(
                "Opening sensor\\film.csv array file.\n"
                "Validated hybrid-logo-v1 sidecar: 3 observations\n",
                encoding="utf-8",
            )
            comskip_log.write_text(
                "CSV file loaded into memory.\n"
                "Finished scanning file.  Starting to build Commercial List.\n",
                encoding="utf-8",
            )
            result = validate_csv_rescore_log(command_log, comskip_log)
            self.assertTrue(all(result.values()))
            comskip_log.write_text(
                comskip_log.read_text(encoding="utf-8") + "3 frames decoded in 0.1 seconds\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "video_decode_absent"):
                validate_csv_rescore_log(command_log, comskip_log)

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
