from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from comskip_final import (
    COMMERCIAL_MACRO_PROFILE,
    DEFAULT_FULL_PROFILE,
    FILM_DIRECTORY_NAME,
    PUBLIC_FAST_PROFILE,
    RUN_DIRECTORY_NAME,
    WEDO_MOVIES_PROFILE,
    ExitTrace,
    application_dir,
    complete_comskip_txt,
    copy_final_outputs,
    create_run_workspace,
    create_diagnostic_package,
    executable_default,
    main,
    macro_result_is_empty,
    parse_args,
    run_automatic_full_analysis_fallback,
    runtime_root,
    select_processing_decision,
)
from multiwindow_logo_experiment import (
    DIAGNOSTIC_NAME,
    FINAL_OUTPUT_NAME,
    SELECTED_MASK_NAME,
    learning_window_artifacts,
)


class ComskipFinalTests(unittest.TestCase):
    def test_processing_profiles_are_exclusive_and_closed(self) -> None:
        common = {
            "fast_mode_channels": {"arte"},
            "macro_mode_channels": {"nitro"},
            "requested_wedo_movies_mode": "active",
            "requested_commercial_edge_refiner_mode": "active",
        }
        public = select_processing_decision(
            video=Path("Film_arte_hd.mp4"),
            requested_full_analysis=True,
            **common,
        )
        self.assertEqual(PUBLIC_FAST_PROFILE, public.profile)
        self.assertEqual("arte", public.fast_mode_channel)
        self.assertEqual("off", public.commercial_edge_refiner_mode)

        wedo = select_processing_decision(
            video=Path("Film_wedo-movies_hd.mp4"),
            requested_full_analysis=True,
            **common,
        )
        self.assertEqual(WEDO_MOVIES_PROFILE, wedo.profile)
        self.assertEqual("active", wedo.wedo_movies_mode)
        self.assertIsNone(wedo.fast_mode_channel)
        self.assertIsNone(wedo.macro_mode_channel)
        self.assertEqual("off", wedo.commercial_edge_refiner_mode)

        macro = select_processing_decision(
            video=Path("Film_nitro_hd.mp4"),
            requested_full_analysis=False,
            **common,
        )
        self.assertEqual(COMMERCIAL_MACRO_PROFILE, macro.profile)
        self.assertEqual("nitro", macro.macro_mode_channel)

        forced_full = select_processing_decision(
            video=Path("Film_nitro_hd.mp4"),
            requested_full_analysis=True,
            **common,
        )
        self.assertEqual(DEFAULT_FULL_PROFILE, forced_full.profile)
        self.assertEqual("active", forced_full.commercial_edge_refiner_mode)

    def test_empty_macro_result_requires_automatic_full_analysis(self) -> None:
        self.assertTrue(macro_result_is_empty({"final_stage_intervals": []}))
        self.assertFalse(macro_result_is_empty({"final_stage_intervals": [[1, 100]]}))

    def test_automatic_fallback_discards_macro_outputs_and_marks_full_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "Film_tele-5_hq.mp4"
            video.write_bytes(b"video")
            output_root = root / "work"
            film_root = output_root / FILM_DIRECTORY_NAME
            (film_root / "final").mkdir(parents=True)
            (film_root / "final" / "old.txt").write_text("macro", encoding="utf-8")
            sight_root = output_root / "review"
            sight_root.mkdir()
            traces = []
            run_args = argparse.Namespace(
                output_root=output_root,
                sight_root=sight_root,
                film_dirname=FILM_DIRECTORY_NAME,
                exit_trace=lambda stage, **details: traces.append((stage, details)),
            )

            def full_runner(args, key, selected_video):
                self.assertFalse((args.output_root / args.film_dirname / "final" / "old.txt").exists())
                self.assertEqual(video.stem, key)
                self.assertEqual(video, selected_video)
                target = args.output_root / args.film_dirname
                final = target / "final"
                final.mkdir(parents=True)
                (final / "final.log").write_text("full\n", encoding="utf-8")
                return {"final_stage_intervals": [[10, 20]], "runtime_seconds": {"total": 100.0}}

            result = run_automatic_full_analysis_fallback(
                run_args=run_args,
                video=video,
                reason="MAKROMODUS_OHNE_SCHNITTBLOCK",
                macro_runtime_seconds=17.5,
                full_runner=full_runner,
            )

            self.assertEqual(117.5, result["runtime_seconds"]["total"])
            self.assertTrue(result["automatic_full_analysis_fallback"]["activated"])
            diagnostic = json.loads((film_root / DIAGNOSTIC_NAME).read_text(encoding="utf-8"))
            self.assertEqual(
                "MAKROMODUS_OHNE_SCHNITTBLOCK",
                diagnostic["automatic_full_analysis_fallback"]["reason"],
            )
            self.assertEqual(
                ["MACRO_AUTOMATIC_FULL_ANALYSIS_START", "MACRO_AUTOMATIC_FULL_ANALYSIS_END"],
                [stage for stage, _details in traces],
            )

    def test_v3_defaults_general_edge_refiner_to_active(self) -> None:
        with mock.patch.object(sys, "argv", ["comskip-final.exe"]):
            parsed = parse_args()
            self.assertEqual(parsed.commercial_edge_refiner_mode, "active")
            self.assertFalse(parsed.full_analysis)
            self.assertEqual(parsed.fast_mode_time_budget, 55.0)

    def test_frozen_application_uses_actual_started_executable_directory(self) -> None:
        executable = Path(r"E:\VideoTools\ComSkip\comskip-final.exe")
        with mock.patch("comskip_final.sys.frozen", True, create=True), mock.patch(
            "comskip_final.sys.executable", str(executable)
        ):
            self.assertEqual(application_dir(), executable.parent)

    def test_frozen_component_never_falls_back_to_path(self) -> None:
        executable = Path(r"E:\VideoTools\ComSkip\comskip-final.exe")
        with mock.patch("comskip_final.sys.frozen", True, create=True), mock.patch(
            "comskip_final.sys.executable", str(executable)
        ), mock.patch(
            "comskip_final.shutil.which",
            return_value=r"D:\SysOp\Privat\SOFTWARE\_Videobearbeitung\ComSkip\comskip.exe",
        ) as which:
            self.assertEqual(executable_default("comskip.exe"), executable.parent / "comskip.exe")
            which.assert_not_called()

    def test_runtime_root_uses_system_temp(self) -> None:
        self.assertEqual(runtime_root(), Path(tempfile.gettempdir()) / "ComskipFinal")

    def test_multiple_runs_receive_distinct_short_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runs_root = Path(directory) / RUN_DIRECTORY_NAME
            first_id, first_root = create_run_workspace(runs_root)
            second_id, second_root = create_run_workspace(runs_root)
            self.assertRegex(first_id, r"^[0-9a-f]{10}$")
            self.assertRegex(second_id, r"^[0-9a-f]{10}$")
            self.assertNotEqual(first_id, second_id)
            self.assertEqual(first_root, runs_root / first_id)
            self.assertEqual(second_root, runs_root / second_id)

    def test_learning_outputs_can_be_created_below_short_runtime_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            film_root = Path(directory) / RUN_DIRECTORY_NAME / "a7f31c92d4" / FILM_DIRECTORY_NAME
            artifacts = learning_window_artifacts(film_root, 1)
            artifacts.root.mkdir(parents=True)
            artifacts.mask.write_text("mask", encoding="utf-8")
            artifacts.raw.write_text("raw", encoding="utf-8")
            self.assertTrue(artifacts.mask.is_file())
            self.assertTrue(artifacts.raw.is_file())
            self.assertEqual(artifacts.mask.name, "w1.logo.txt")
            self.assertEqual(artifacts.raw.name, "w1.logo-raw.csv")

    def test_complete_txt_requires_completion_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.txt"
            path.write_text("partial\n", encoding="utf-8")
            self.assertFalse(complete_comskip_txt(path))
            path.write_text("FILE PROCESSING COMPLETE 100 FRAMES AT 2500\n", encoding="utf-8")
            self.assertTrue(complete_comskip_txt(path))

    def test_txt_is_copied_only_after_other_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "Film mit Leerzeichen und Umlaut Ä.mp4"
            video.write_bytes(b"video")
            film_root = root / "work" / FILM_DIRECTORY_NAME
            final_root = film_root / "final"
            final_root.mkdir(parents=True)
            (final_root / f"{FINAL_OUTPUT_NAME}.txt").write_text(
                "FILE PROCESSING COMPLETE 100 FRAMES AT 2500\n", encoding="utf-8"
            )
            (final_root / f"{FINAL_OUTPUT_NAME}.edl").write_text("1 2 0\n", encoding="utf-8")
            (film_root / SELECTED_MASK_NAME).write_text("mask\n", encoding="utf-8")
            (film_root / DIAGNOSTIC_NAME).write_text("{}", encoding="utf-8")
            copied = copy_final_outputs(video, film_root, {})
            self.assertEqual(copied[-1], video.with_suffix(".txt"))
            self.assertTrue(video.with_suffix(".edl").is_file())
            self.assertTrue(video.with_name(video.stem + ".logo.txt").is_file())
            diagnostic = video.with_name(video.stem + ".comskip-final.json")
            payload = json.loads(diagnostic.read_text(encoding="utf-8"))
            self.assertIn(str(video.with_suffix(".txt")), payload["portable_outputs"])

    def test_publication_removes_stale_outputs_from_previous_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "Film_wedo-movies_hd.mp4"
            video.write_bytes(b"video")
            for suffix in (
                ".edl",
                ".log",
                ".logo.txt",
                ".schnellmodus.txt",
                ".makromodus.txt",
                ".pruefmarker.txt",
                ".comskip-final.json",
            ):
                video.with_name(video.stem + suffix).write_text("stale", encoding="utf-8")

            film_root = root / "work" / FILM_DIRECTORY_NAME
            final_root = film_root / "final"
            final_root.mkdir(parents=True)
            (final_root / f"{FINAL_OUTPUT_NAME}.txt").write_text(
                "FILE PROCESSING COMPLETE 100 FRAMES AT 2500\n", encoding="utf-8"
            )

            copy_final_outputs(video, film_root, {"processing_mode": "wedo_movies_v3"})

            self.assertTrue(video.with_suffix(".txt").is_file())
            for suffix in (
                ".edl",
                ".log",
                ".logo.txt",
                ".schnellmodus.txt",
                ".makromodus.txt",
                ".pruefmarker.txt",
                ".comskip-final.json",
            ):
                self.assertFalse(video.with_name(video.stem + suffix).exists(), suffix)

    def test_diagnostic_package_excludes_video_and_raw_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / ("Sehr langer Filmname mit Leerzeichen und Umlaut Ü-" + "x" * 80 + ".mp4")
            video.write_bytes(b"video")
            work = root / RUN_DIRECTORY_NAME / "a7f31c92d4"
            nested = work / FILM_DIRECTORY_NAME / "learn" / "w1"
            nested.mkdir(parents=True)
            (nested / "cmd.log").write_text("log", encoding="utf-8")
            (work / "sensor.logo-raw.csv").write_text("large", encoding="utf-8")
            (work / "sensor.csv").write_text("full framearray", encoding="utf-8")
            (work / "hybrid-logo.jsonl").write_text("large", encoding="utf-8")
            (work / "clip.mp4").write_bytes(b"clip")
            try:
                raise RuntimeError("boom")
            except RuntimeError as exc:
                package = create_diagnostic_package(video, work, exc, run_id="a7f31c92d4")
            with zipfile.ZipFile(package) as archive:
                names = archive.namelist()
                failure = json.loads(archive.read("failure.json"))
            self.assertIn("failure.json", names)
            self.assertIn("run/learn/w1/cmd.log", names)
            self.assertNotIn("sensor.logo-raw.csv", names)
            self.assertNotIn("sensor.csv", names)
            self.assertNotIn("hybrid-logo.jsonl", names)
            self.assertNotIn("clip.mp4", names)
            self.assertTrue(package.name.startswith("a7f31c92d4-"))
            self.assertNotIn(video.stem, package.name)
            self.assertEqual(failure["video"], str(video))
            self.assertEqual(failure["run_id"], "a7f31c92d4")
            self.assertTrue(all(video.stem not in name for name in names))
            package.unlink()

    def test_trace_filename_is_short_but_record_keeps_full_video_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "comskip_final.runtime_root", return_value=Path(directory)
        ):
            video = Path(directory) / ("Langer Film Ä " + "z" * 100 + ".mp4")
            trace = ExitTrace(video, "a7f31c92d4")
            record = json.loads(trace.path.read_text(encoding="utf-8").splitlines()[0])
            self.assertTrue(trace.path.name.startswith("a7f31c92d4-"))
            self.assertNotIn(video.stem, trace.path.name)
            self.assertEqual(record["video"], str(video))

    def test_successful_main_publishes_txt_last_and_exits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / ("Praxistest Film mit Leerzeichen und Umlaut Ö " + "x" * 60 + ".mp4")
            video.write_bytes(b"video")
            components = {}
            for name in ("comskip.exe", "comskip.ini", "ffmpeg.exe", "ffprobe.exe"):
                path = root / name
                path.write_bytes(b"component")
                components[name] = path
            runtime = root / "runtime"
            child_processes: list[subprocess.Popen] = []

            def successful_run(run_args, key, _video):
                child = subprocess.Popen(
                    [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                child_processes.append(child)
                stdout, stderr = child.communicate(b"pipe-data", timeout=10)
                self.assertEqual(stdout, b"pipe-data")
                self.assertEqual(stderr, b"")
                self.assertEqual(child.returncode, 0)
                self.assertEqual(key, video.stem)
                self.assertEqual(run_args.film_dirname, FILM_DIRECTORY_NAME)
                self.assertNotIn(video.stem, str(run_args.output_root))
                film_root = run_args.output_root / run_args.film_dirname
                final_root = film_root / "final"
                final_root.mkdir(parents=True)
                (final_root / f"{FINAL_OUTPUT_NAME}.txt").write_text(
                    "FILE PROCESSING COMPLETE 100 FRAMES AT 2500\n1 2\n", encoding="utf-8"
                )
                (final_root / f"{FINAL_OUTPUT_NAME}.edl").write_text("1 2 0\n", encoding="utf-8")
                (final_root / f"{FINAL_OUTPUT_NAME}.log").write_text("complete\n", encoding="utf-8")
                (film_root / SELECTED_MASK_NAME).write_text("mask\n", encoding="utf-8")
                (film_root / DIAGNOSTIC_NAME).write_text("{}", encoding="utf-8")
                run_args.exit_trace("TEST_CHILD_REAPED", pid=child.pid, return_code=child.returncode)
                return {"final_stage_intervals": [[1, 2]]}

            parsed = argparse.Namespace(
                video=video,
                comskip=components["comskip.exe"],
                ini=components["comskip.ini"],
                ffmpeg=components["ffmpeg.exe"],
                ffprobe=components["ffprobe.exe"],
                window_seconds=120.0,
                keep_work_dir=False,
                version=False,
                full_analysis=True,
                fast_mode_time_budget=55.0,
            )
            baseline_threads = {thread.ident for thread in threading.enumerate()}
            with mock.patch("comskip_final.parse_args", return_value=parsed), mock.patch(
                "comskip_final.runtime_root", return_value=runtime
            ), mock.patch("comskip_final.run_film", side_effect=successful_run):
                self.assertEqual(main(), 0)

            self.assertTrue(video.with_suffix(".txt").is_file())
            self.assertTrue(complete_comskip_txt(video.with_suffix(".txt")))
            self.assertTrue(video.with_suffix(".edl").is_file())
            self.assertTrue(video.with_suffix(".log").is_file())
            self.assertTrue(video.with_name(video.stem + ".logo.txt").is_file())
            self.assertFalse((runtime / RUN_DIRECTORY_NAME).exists())
            self.assertTrue(all(process.poll() == 0 for process in child_processes))
            self.assertEqual({thread.ident for thread in threading.enumerate()}, baseline_threads)
            trace_path = next((runtime / "traces").glob("*.jsonl"))
            self.assertNotIn(video.stem, trace_path.name)
            records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["video"], str(video.resolve()))
            self.assertRegex(records[0]["run_id"], r"^[0-9a-f]{10}$")
            temporary_names = [
                Path(record["temporary"]).name for record in records if "temporary" in record
            ]
            self.assertTrue(temporary_names)
            self.assertTrue(all(re.match(r"^\.cf-.*\.tmp$", name) for name in temporary_names))
            self.assertTrue(all(video.stem not in name for name in temporary_names))
            stages = [record["stage"] for record in records]
            self.assertLess(stages.index("EDL_ATOMIC_REPLACE_END"), stages.index("TXT_ATOMIC_REPLACE_END"))
            self.assertLess(stages.index("LOG_ATOMIC_REPLACE_END"), stages.index("TXT_ATOMIC_REPLACE_END"))
            self.assertLess(stages.index("LOGO_TXT_ATOMIC_REPLACE_END"), stages.index("TXT_ATOMIC_REPLACE_END"))
            self.assertLess(stages.index("WORKSPACE_CLEANUP_END"), stages.index("COMSKIP_FINAL_MAIN_RETURN"))


if __name__ == "__main__":
    unittest.main()
