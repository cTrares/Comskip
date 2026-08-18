from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from comskip_final import (
    application_dir,
    complete_comskip_txt,
    copy_final_outputs,
    create_diagnostic_package,
    executable_default,
    main,
    runtime_root,
)


class ComskipFinalTests(unittest.TestCase):
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
            video = root / "film.mp4"
            video.write_bytes(b"video")
            film_root = root / "work" / "film"
            final_root = film_root / "final"
            final_root.mkdir(parents=True)
            (final_root / "film.txt").write_text(
                "FILE PROCESSING COMPLETE 100 FRAMES AT 2500\n", encoding="utf-8"
            )
            (final_root / "film.edl").write_text("1 2 0\n", encoding="utf-8")
            (film_root / "selected-comskip-logo.txt").write_text("mask\n", encoding="utf-8")
            (film_root / "multiwindow_diagnostic.json").write_text("{}", encoding="utf-8")
            copied = copy_final_outputs(video, film_root, {})
            self.assertEqual(copied[-1], root / "film.txt")
            self.assertTrue((root / "film.edl").is_file())
            self.assertTrue((root / "film.logo.txt").is_file())
            payload = json.loads((root / "film.comskip-final.json").read_text(encoding="utf-8"))
            self.assertIn(str(root / "film.txt"), payload["portable_outputs"])

    def test_diagnostic_package_excludes_video_and_raw_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "film.mp4"
            video.write_bytes(b"video")
            work = root / "work"
            work.mkdir()
            (work / "command.log").write_text("log", encoding="utf-8")
            (work / "sensor.logo-raw.csv").write_text("large", encoding="utf-8")
            (work / "sensor.csv").write_text("full framearray", encoding="utf-8")
            (work / "hybrid-logo.jsonl").write_text("large", encoding="utf-8")
            (work / "clip.mp4").write_bytes(b"clip")
            try:
                raise RuntimeError("boom")
            except RuntimeError as exc:
                package = create_diagnostic_package(video, work, exc)
            with zipfile.ZipFile(package) as archive:
                names = archive.namelist()
            self.assertIn("failure.json", names)
            self.assertIn("command.log", names)
            self.assertNotIn("sensor.logo-raw.csv", names)
            self.assertNotIn("sensor.csv", names)
            self.assertNotIn("hybrid-logo.jsonl", names)
            self.assertNotIn("clip.mp4", names)
            package.unlink()

    def test_successful_main_publishes_txt_last_and_exits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "film.mp4"
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
                film_root = run_args.output_root / key
                final_root = film_root / "final"
                final_root.mkdir(parents=True)
                (final_root / "film.txt").write_text(
                    "FILE PROCESSING COMPLETE 100 FRAMES AT 2500\n1 2\n", encoding="utf-8"
                )
                (final_root / "film.edl").write_text("1 2 0\n", encoding="utf-8")
                (final_root / "film.log").write_text("complete\n", encoding="utf-8")
                (film_root / "selected-comskip-logo.txt").write_text("mask\n", encoding="utf-8")
                (film_root / "multiwindow_diagnostic.json").write_text("{}", encoding="utf-8")
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
            )
            baseline_threads = {thread.ident for thread in threading.enumerate()}
            with mock.patch("comskip_final.parse_args", return_value=parsed), mock.patch(
                "comskip_final.runtime_root", return_value=runtime
            ), mock.patch("comskip_final.run_film", side_effect=successful_run):
                self.assertEqual(main(), 0)

            self.assertTrue((root / "film.txt").is_file())
            self.assertTrue(complete_comskip_txt(root / "film.txt"))
            self.assertFalse((runtime / "runs").exists())
            self.assertTrue(all(process.poll() == 0 for process in child_processes))
            self.assertEqual({thread.ident for thread in threading.enumerate()}, baseline_threads)
            trace_path = next((runtime / "traces").glob("film-*.jsonl"))
            stages = [json.loads(line)["stage"] for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertLess(stages.index("EDL_ATOMIC_REPLACE_END"), stages.index("TXT_ATOMIC_REPLACE_END"))
            self.assertLess(stages.index("LOG_ATOMIC_REPLACE_END"), stages.index("TXT_ATOMIC_REPLACE_END"))
            self.assertLess(stages.index("LOGO_TXT_ATOMIC_REPLACE_END"), stages.index("TXT_ATOMIC_REPLACE_END"))
            self.assertLess(stages.index("WORKSPACE_CLEANUP_END"), stages.index("COMSKIP_FINAL_MAIN_RETURN"))


if __name__ == "__main__":
    unittest.main()
