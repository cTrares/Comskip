import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import wedo_fallback_diagnostic as diag


class FallbackDiagnosticTests(unittest.TestCase):
    def test_gate_distinguishes_empty_windows_from_excess_coverage(self):
        self.assertEqual(diag.gate_details([], [], 0)["reason"], "NO_CANDIDATE_WINDOWS")
        self.assertEqual(diag.gate_details([], [(0, 60)], .6)["reason"], "LOCAL_SCAN_ACCEPTED")
        self.assertEqual(diag.gate_details([], [(0, 61)], .61)["reason"], "LOCAL_COVERAGE_EXCEEDED")

    def test_exactly_two_known_files_are_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*diag.TARGETS, "Other_wedo-movies_hd.mp4", "Other_arte_hd.mp4"):
                (root/name).write_bytes(b"untouched")
            self.assertEqual([p.name for p in diag.selected_videos(root)], list(diag.TARGETS))
            (root/diag.TARGETS[1]).unlink()
            with self.assertRaises(FileNotFoundError):
                diag.selected_videos(root)

    def test_window_evidence_preserves_actual_rules_and_identifies_missing_red_block(self):
        rows = [{"seconds": 200, "logo_present": False, "red_layout": False},
                {"seconds": 800, "logo_present": True, "red_layout": True}]
        result = diag.window_evidence(rows, 1200, [
            {"first_layout_second": 780, "last_layout_second": 890},
            {"first_layout_second": 1000, "last_layout_second": 1110}])
        self.assertEqual(result["variants"]["actual_v3"]["windows_seconds"], [(45, 355), (645, 955)])
        self.assertEqual(result["variants"]["red_only_explanation_not_applied"]["windows_seconds"], [(645, 955)])
        self.assertEqual([r["fully_inside_discovery_window"] for r in result["full_layout_candidate_coverage"]], [True, False])

    def test_real_video_diagnosis_exports_evidence_without_changing_existing_results(self):
        portable = Path(__file__).resolve().parents[2] / "dist/ComSkip"
        ffmpeg = portable / "ffmpeg.exe"
        if not ffmpeg.is_file():
            self.skipTest("Portable FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / diag.TARGETS[0]
            subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=black:s=320x180:r=5:d=600",
                "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:enable='between(t,203,312.8)'",
                "-c:v", "libx264", "-preset", "ultrafast", "-an", str(video)],
                check=True, capture_output=True, timeout=30)
            prior = video.with_suffix(".txt")
            prior.write_bytes(b"existing cut list must not be overwritten")
            original = video.read_bytes()

            def learning(**kwargs):
                artifact = kwargs["film_root"] / "macro-comskip-logo/window-0"
                artifact.mkdir(parents=True)
                (artifact/"temporary.mp4").write_bytes(b"generated clip")
                return mock.Mock(), lambda times: {t: .1 for t in times}, .8, {}

            output = root / "diagnosis"
            with mock.patch.object(diag.sparse, "learn_macro_overlay_via_comskip", side_effect=learning):
                result = diag.diagnose_film(video, output, portable)
            self.assertEqual(result["status"], "DIAGNOSED", result.get("error"))
            self.assertEqual(result["discovery"]["reason"], "LOCAL_COVERAGE_EXCEEDED")
            self.assertEqual(result["discovery"]["coverage"], 1)
            self.assertEqual(result["discovery"]["sample_count"], 30)
            self.assertEqual(len(result["full_red_layout_control"]["candidates"]), 1)
            self.assertTrue(result["window_evidence"]["full_layout_candidate_coverage"][0]["fully_inside_discovery_window"])
            self.assertEqual(video.read_bytes(), original)
            self.assertEqual(prior.read_bytes(), b"existing cut list must not be overwritten")
            self.assertTrue((output/"samples/000200.png").is_file())
            self.assertFalse(list(output.rglob("*.mp4")))
            with zipfile.ZipFile(diag.create_bundle(output)) as archive:
                self.assertIn("diagnostic.json", archive.namelist())
                self.assertIn("samples.csv", archive.namelist())
                self.assertFalse(any(name.endswith(".mp4") for name in archive.namelist()))
                self.assertEqual(json.loads(archive.read("diagnostic.json"))["discovery"]["coverage"], 1)

    def test_errors_are_saved_and_do_not_become_a_fallback_guess(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/diag.TARGETS[0]
            source.write_bytes(b"input")
            with mock.patch.object(diag.sparse, "probe_video", side_effect=RuntimeError("decoder failed")):
                result = diag.diagnose_film(source, root/"out", root)
            self.assertEqual(result["status"], "ERROR")
            self.assertNotIn("discovery", result)
            self.assertIn("decoder failed", (root/"out/error.log").read_text())


if __name__ == "__main__":
    unittest.main()
