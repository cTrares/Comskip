from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import wedo_native_tail as native
import wedo_sparse_mode as sparse
import wedo_movies_detector as detector


class NativeTailTests(unittest.TestCase):
    def test_window_has_context_but_stays_inside_video(self):
        metadata = SimpleNamespace(fps=25, total_frames=10000, duration_seconds=400.02)
        self.assertEqual(native.tail_window(120, metadata), (90, 330))
        self.assertEqual(native.tail_window(395, metadata), (365, 400))
        with self.assertRaises(RuntimeError):
            native.tail_window(400, metadata)

    def test_invalid_window_never_starts_a_decoder(self):
        metadata = SimpleNamespace(fps=25, total_frames=10000, duration_seconds=400.02)
        with mock.patch.object(native, "run_logged") as run:
            with self.assertRaises(RuntimeError):
                native.measure_tail(video=Path("video"), metadata=metadata, layout_end=400,
                                    mask=Path("mask"), ffmpeg=Path("ffmpeg"), comskip=Path("comskip"),
                                    ini=Path("ini"), output=Path("must-not-be-created"))
            run.assert_not_called()

    def test_noninteger_cadence_falls_back_instead_of_shifting_native_sampling(self):
        with self.assertRaises(RuntimeError):
            native.tail_window(120, SimpleNamespace(fps=29.97, total_frames=12000, duration_seconds=400.4))

    def test_native_return_uses_existing_bumper_and_missing_return_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sidecar = root / "native.jsonl"
            sidecar.write_text('{"record_type":"observation","comskip_frame":6250,'
                               '"time_seconds":250,"comskip_local_state":"PRESENT"}\n')
            metadata = SimpleNamespace(fps=25, total_frames=10000, duration_seconds=400)
            candidate = {"start_seconds": 10, "end_seconds": 122, "last_layout_second": 119}
            bumper = SimpleNamespace(commercial_end_frame=6000, movie_start_frame=6001,
                                     scene_change_score=.8, red_fraction=.1, white_fraction=.1, logo_mask_recall=.95)
            with mock.patch.object(sparse, "measure_tail", return_value=(sidecar, {})), \
                    mock.patch.object(detector, "_find_branded_bumper_cut", return_value=bumper) as find:
                report = {"candidates": [candidate.copy()]}
                sparse.refine_tails(report, root / "video", metadata, root / "mask",
                                    ffmpeg=root, comskip=root, ini=root, film_root=root)
                self.assertEqual(report["candidates"][0]["end_seconds"], 240)
                self.assertEqual(find.call_args.kwargs["logo_return_seconds"], 250)
                sidecar.write_text(sidecar.read_text().replace('"PRESENT"', '"ABSENT"'))
                with self.assertRaisesRegex(RuntimeError, "Keine sichere native"):
                    sparse.refine_tails({"candidates": [candidate.copy()]}, root / "video", metadata,
                                        root / "mask", ffmpeg=root, comskip=root, ini=root, film_root=root)

    def test_broken_native_timeline_cannot_accept_early_logo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.csv"
            for bad in ("1,0,1,1\n", "1,0,1,0\n2,0.04,1,0\n", "1,0,1,1\n3,0.08,1,1\n"):
                raw.write_text("frame,time_seconds,comskip_present,global_logo_enabled\n" + bad)
                with self.assertRaises(RuntimeError):
                    native.native_sidecar(raw, root / "sidecar.jsonl", 90, 330, 25)

    def test_native_clip_matches_full_run_and_ignores_short_preview_logo(self):
        portable = Path(__file__).resolve().parents[2] / "dist/ComSkip"
        ffmpeg, comskip, ini = (portable / name for name in ("ffmpeg.exe", "comskip.exe", "comskip.ini"))
        if not ffmpeg.is_file() or not comskip.is_file():
            self.skipTest("Portable native tools unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, mask = root / "synthetic.mp4", root / "selected.logo.txt"
            # A fixed vertical logo edge: short appearance in a preview, then
            # a sustained return to the film. The source has non-aligned GOPs.
            mask.write_bytes(b"logoMinX=280\nlogoMaxX=280\nlogoMinY=24\nlogoMaxY=44\n"
                             b"picWidth=320\npicHeight=180\n\x82\n" + b"|\n" * 21)
            native.run_logged([
                str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=gray:s=320x180:r=25:d=350",
                "-vf", "drawbox=x=280:y=20:w=20:h=30:color=white:t=fill:enable='lt(t,40)+between(t,160,162)+gte(t,200)'",
                "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-g", "137", str(video),
            ], root / "generate.log")
            native.run_logged([str(comskip), "--ini", str(ini), "--output", str(root),
                               "--output-filename", "full", "--logo", str(mask), "--logo-raw", str(video)],
                              root / "full-run.log", accepted=(0, 1))
            full_sidecar = root / "full.jsonl"
            native.native_sidecar(root / "full.logo-raw.csv", full_sidecar, 0, 350, 25)
            metadata = SimpleNamespace(fps=25, total_frames=8750, duration_seconds=350.02)
            report = {"activation": {"matched": True}, "duration_seconds": 350,
                      "candidates": [{"start_seconds": 10, "end_seconds": 122, "last_layout_second": 119}]}
            expected = detector.extend_wedo_movies_program_hint_tails(report, sidecar_path=full_sidecar)
            with mock.patch.object(detector, "_find_branded_bumper_cut", return_value=None):
                sparse.refine_tails(report, video, metadata, mask, ffmpeg=ffmpeg, comskip=comskip,
                                    ini=ini, film_root=root)
            actual = report["candidates"][0]
            self.assertGreaterEqual(actual["end_seconds"], 199)
            self.assertLess(actual["end_seconds"], 211)
            self.assertEqual(actual["end_seconds"], expected["candidates"][0]["end_seconds"])
            self.assertEqual(actual["program_hint_tail"]["logo_measurement"], "comskip-native-v1-local")
            with (root / "native-tails/tail-01/native.logo-raw.csv").open() as source:
                rows = list(csv.DictReader(source))
            # Raw edge score is strong during the short preview, but the native
            # temporal state still rejects it as the end of the commercial.
            preview = [r for r in rows if 160 <= float(r["time_seconds"]) + 90 < 162]
            self.assertTrue(any(float(r["comskip_good_edge"]) > .75 for r in preview))
            self.assertTrue(all(int(r["comskip_present"]) == 0 for r in preview))
            self.assertFalse((root / "native-tails/tail-01/tail.mp4").exists())


if __name__ == "__main__":
    unittest.main()
