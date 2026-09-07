from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wedo_sparse_mode as sparse
from public_broadcaster_fast_mode import VideoMetadata


class WedoSparseTests(unittest.TestCase):
    def test_single_logo_miss_survives_and_windows_merge(self):
        rows = [dict(seconds=s, logo_present=s not in (200, 220, 800), red_layout=False)
                for s in range(0, 1000, 20)]
        self.assertEqual(sparse.candidate_windows(rows, 1000), [(45, 375), (645, 955)])

    def test_red_layout_opens_window_even_when_logo_is_present(self):
        rows = [dict(seconds=10, logo_present=True, red_layout=True),
                dict(seconds=990, logo_present=True, red_layout=True)]
        self.assertEqual(sparse.candidate_windows(rows, 1000), [(0, 165), (835, 1000)])

    def test_non_wedo_is_refused_before_any_io(self):
        with self.assertRaises(ValueError):
            sparse.run_wedo_sparse_mode(argparse.Namespace(wedo_movies_mode="active"),
                                        "film", Path("Film_arte_hd.mp4"))

    def test_outer_crops_never_absorb_a_confirmed_internal_block(self):
        metadata = argparse.Namespace(duration_seconds=1000, fps=25, total_frames=25000)
        rows = [dict(seconds=100, logo_present=True, red_layout=False),
                dict(seconds=800, logo_present=True, red_layout=False)]
        self.assertEqual(sparse.outer_intervals(rows, metadata, []), [(1, 2500), (20500, 25000)])
        cuts = [dict(start_seconds=50, end_seconds=120), dict(start_seconds=850, end_seconds=960)]
        self.assertEqual(sparse.outer_intervals(rows, metadata, cuts), [])

    def test_fallback_starts_with_clean_legacy_directory_and_records_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            film = root / "run"
            film.mkdir()
            (film / "partial.txt").write_text("partial")
            args = argparse.Namespace(output_root=root, film_dirname="run")

            def legacy(*_args):
                self.assertFalse(film.exists())
                (film / "final").mkdir(parents=True)
                (film / "final" / "final.log").write_text("legacy")
                return {"runtime_seconds": {"total": 3}, "final_stage_intervals": [[5, 10]]}

            with mock.patch.object(sparse, "run_wedo_sparse_mode", side_effect=RuntimeError("uncertain")):
                result = sparse.run_wedo_with_fallback(args, "film", Path("film_wedo-movies.mp4"), legacy)
            self.assertEqual(result["final_stage_intervals"], [[5, 10]])
            self.assertTrue((root / "wedo-sparse-attempt" / "partial.txt").is_file())
            self.assertIn("uncertain", json.loads((film / "diagnostic.json").read_text())["wedo_sparse_fallback"]["reason"])

    def test_normal_workflow_uses_final_launcher_for_all_profiles(self):
        source = Path(__file__).resolve().parents[2] / "dist/ComSkip/_Workflow/Werbung entfernen.py"
        entry = runpy.run_path(str(source))
        session = entry["run_session"]
        namespace = session.__globals__
        videos = [Path(name) for name in ("Film_wedo-movies_hd.mp4", "Film_arte_hd.mp4", "Film_pro-7_hq.mp4")]
        calls = []
        replacements = {
            "_SESSION_DIRECTORY": source.parent,
            "find_videos": lambda directory: videos,
            "ask_start_mode": lambda *args: "n",
            "analyse_video": lambda *args: calls.append(args),
            "workflow_status": lambda videos: (3, 0, 3),
        }
        with mock.patch.dict(namespace, replacements), mock.patch("builtins.input", return_value=""):
            self.assertEqual(session(), 0)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call[0].name == "comskip-final.exe" for call in calls))
        self.assertEqual([call[1] for call in calls], videos)

    def test_local_decoder_preserves_absolute_time_and_excludes_other_windows(self):
        ffmpeg = Path(__file__).resolve().parents[2] / "dist/ComSkip/ffmpeg.exe"
        if not ffmpeg.is_file():
            self.skipTest("Portable FFmpeg not available")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "synthetic_wedo-movies_hd.mp4"
            # Two red blocks, but only the first is inside the requested window.
            subprocess.run([
                str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=black:s=320x180:r=5:d=600",
                "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:enable='between(t,203,312.8)+between(t,450,559.8)'",
                "-c:v", "libx264", "-preset", "ultrafast", "-an", str(video),
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            report = sparse.scan_layout_windows(video, ffmpeg, [(180, 340)], 600, root)
            self.assertEqual(report["layout_samples_measured"], 160)
            self.assertEqual(len(report["candidates"]), 1)
            candidate = report["candidates"][0]
            self.assertAlmostEqual(candidate["first_layout_second"], 203, delta=1)
            self.assertAlmostEqual(candidate["last_layout_second"], 312, delta=1)

    def test_successful_run_publishes_only_confirmed_red_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(output_root=root, film_dirname="run", ffmpeg=Path("ffmpeg"),
                                      ffprobe=Path("ffprobe"), comskip=Path("comskip"), ini=Path("ini"),
                                      wedo_movies_mode="active")
            metadata = VideoMetadata(
                duration_seconds=1200.02, fps=25, total_frames=30000, width=320, height=180)
            report = {"candidates": [dict(start_seconds=399, end_seconds=513, last_layout_second=510)],
                      "duration_seconds": 1200, "activation": {"matched": True}}
            def score(times):
                self.assertLess(max(times), 1200, "Must not read the exclusive video endpoint")
                return {t: 0.1 if 400 <= t <= 500 else 0.8 for t in times}
            with mock.patch.object(sparse, "probe_video", return_value=metadata), \
                    mock.patch.object(sparse, "learn_macro_overlay_via_comskip", return_value=(mock.Mock(), score, .8, {})), \
                    mock.patch.object(sparse.cv2, "VideoCapture", return_value=mock.Mock()), \
                    mock.patch.object(sparse, "read_frame_at", return_value=sparse.np.zeros((180, 320, 3), dtype="uint8")), \
                    mock.patch.object(sparse, "scan_layout_windows", return_value=report), \
                    mock.patch.object(sparse, "refine_tails"):
                result = sparse.run_wedo_sparse_mode(args, "film", root / "Film_wedo-movies_hd.mp4")
            self.assertEqual(result["processing_mode"], sparse.PROCESSING_MODE)
            self.assertEqual(result["final_stage_intervals"], [[1, 1], [9975, 12825], [30000, 30000]])
            self.assertEqual(len(result["coarse_observations"]), 60)
            self.assertIn("FILE PROCESSING COMPLETE 30000", (root / "run/final/final.txt").read_text())


if __name__ == "__main__":
    unittest.main()
