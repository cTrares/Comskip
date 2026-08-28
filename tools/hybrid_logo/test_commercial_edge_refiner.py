from __future__ import annotations

import json
import os
import shutil
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from commercial_edge_refiner import (
    ABSENT,
    PRESENT,
    analyze_commercial_edges,
    apply_commercial_edge_extensions,
    read_comskip_logo_runs,
)

TEST_TEMP_ROOT = Path(__file__).resolve().parents[2] / "_temp" / "unit-test-temp"


@contextmanager
def test_workspace():
    root = TEST_TEMP_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    workspace = (root / uuid.uuid4().hex).resolve()
    if root not in workspace.parents:
        raise RuntimeError("Unsafe unit-test workspace")
    workspace.mkdir()
    try:
        yield workspace
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


class CommercialEdgeRefinerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def write_txt(path: Path, intervals: list[tuple[int, int]], total_frames: int = 229746) -> None:
        payload = f"FILE PROCESSING COMPLETE {total_frames} FRAMES AT  2500\n-------------------\n"
        payload += "".join(f"{start}\t{end}\n" for start, end in intervals)
        path.write_text(payload, encoding="ascii")

    @staticmethod
    def write_sidecar(
        path: Path,
        spans: list[tuple[int, int, str]],
        *,
        reliability: str = "ACCEPTED_BY_EXISTING_GATE",
        padding: int = 0,
    ) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "record_type": "metadata",
                        "global_reliability": {"comskip": reliability},
                    }
                )
                + "\n"
            )
            for start, end, state in spans:
                for frame in range(start, end + 1):
                    handle.write(
                        json.dumps(
                            {
                                "record_type": "observation",
                                "comskip_frame": frame,
                                "time_seconds": frame / 25.0,
                                "comskip_local_state": state,
                                "fusion_state": PRESENT if frame % 2 else "CONFLICT",
                                "diagnostic_padding": "x" * padding,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )

    def test_scream_vi_program_hints_extend_to_last_frame_before_normal_logo_return(self) -> None:
        with test_workspace() as root:
            txt = root / "final.txt"
            sidecar = root / "fusion.jsonl"
            self.write_txt(txt, [(177541, 184124)])
            self.write_sidecar(
                sidecar,
                [
                    (184125, 186024, ABSENT),
                    (186025, 186124, PRESENT),
                ],
            )

            report = analyze_commercial_edges(txt_path=txt, sidecar_path=sidecar, fps=25.0)

            self.assertEqual(report["status"], "ANALYZED")
            self.assertFalse(report["video_decode_required"])
            self.assertEqual(len(report["proposals"]), 1)
            proposal = report["proposals"][0]
            self.assertEqual(proposal["original_end_frame"], 184124)
            self.assertEqual(proposal["proposed_end_frame"], 186024)
            self.assertEqual(proposal["normal_logo_return_frame"], 186025)
            self.assertEqual(proposal["extension_frames"], 1900)
            self.assertEqual(proposal["extension_seconds"], 76.0)

    def test_alternate_sensor_or_shifted_branding_never_overrides_fixed_comskip_absence(self) -> None:
        with test_workspace() as root:
            sidecar = root / "fusion.jsonl"
            self.write_sidecar(sidecar, [(100, 199, ABSENT), (200, 249, PRESENT)])
            runs, reliability, _observations = read_comskip_logo_runs(sidecar)
            self.assertEqual(reliability, "ACCEPTED_BY_EXISTING_GATE")
            self.assertEqual([(run.start_frame, run.end_frame, run.state) for run in runs], [
                (100, 199, ABSENT),
                (200, 249, PRESENT),
            ])

    def test_short_false_logo_hit_does_not_end_tail(self) -> None:
        with test_workspace() as root:
            txt = root / "final.txt"
            sidecar = root / "fusion.jsonl"
            self.write_txt(txt, [(10, 99)], total_frames=500)
            self.write_sidecar(
                sidecar,
                [
                    (100, 149, ABSENT),
                    (150, 159, PRESENT),
                    (160, 249, ABSENT),
                    (250, 349, PRESENT),
                ],
            )
            report = analyze_commercial_edges(txt_path=txt, sidecar_path=sidecar, fps=25.0)
            self.assertEqual(report["proposals"][0]["normal_logo_return_frame"], 250)
            self.assertEqual(report["proposals"][0]["proposed_end_frame"], 249)

    def test_missing_confirmed_logo_return_never_extends_blindly(self) -> None:
        with test_workspace() as root:
            txt = root / "final.txt"
            sidecar = root / "fusion.jsonl"
            self.write_txt(txt, [(10, 99)], total_frames=10000)
            self.write_sidecar(sidecar, [(100, 9999, ABSENT)])
            report = analyze_commercial_edges(txt_path=txt, sidecar_path=sidecar, fps=25.0)
            self.assertEqual(report["proposals"], [])

    def test_rejected_global_logo_sensor_never_proposes_change(self) -> None:
        with test_workspace() as root:
            txt = root / "final.txt"
            sidecar = root / "fusion.jsonl"
            self.write_txt(txt, [(10, 99)], total_frames=500)
            self.write_sidecar(
                sidecar,
                [(100, 199, ABSENT), (200, 299, PRESENT)],
                reliability="REJECTED_BY_EXISTING_GATE",
            )
            report = analyze_commercial_edges(txt_path=txt, sidecar_path=sidecar, fps=25.0)
            self.assertEqual(report["status"], "SKIPPED_LOGO_SENSOR_UNAVAILABLE")
            self.assertEqual(report["proposals"], [])

    def test_active_application_rewrites_txt_and_edl_but_preserves_backups(self) -> None:
        with test_workspace() as root:
            txt = root / "final.txt"
            edl = root / "final.edl"
            sidecar = root / "fusion.jsonl"
            self.write_txt(txt, [(177541, 184124)])
            edl.write_text("7101.640\t7364.960\t0\n", encoding="ascii")
            self.write_sidecar(sidecar, [(184125, 186024, ABSENT), (186025, 186124, PRESENT)])
            report = analyze_commercial_edges(txt_path=txt, sidecar_path=sidecar, fps=25.0)

            applied = apply_commercial_edge_extensions(
                txt_path=txt,
                edl_path=edl,
                report=report,
                fps=25.0,
            )

            self.assertIn("177541\t186024", txt.read_text(encoding="ascii"))
            self.assertIn("7440.960", edl.read_text(encoding="ascii"))
            self.assertTrue(Path(applied["pre_refiner_txt"]).is_file())
            self.assertTrue(Path(applied["pre_refiner_edl"]).is_file())

    @unittest.skipUnless(
        os.environ.get("COMSKIP_RUN_EDGE_REFINER_BENCHMARK") == "1",
        "set COMSKIP_RUN_EDGE_REFINER_BENCHMARK=1 for the full-film performance check",
    )
    def test_full_film_sidecar_analysis_stays_below_thirty_seconds(self) -> None:
        with test_workspace() as root:
            txt = root / "final.txt"
            sidecar = root / "fusion.jsonl"
            self.write_txt(txt, [(177541, 184124)], total_frames=230000)
            self.write_sidecar(
                sidecar,
                [
                    (0, 184124, PRESENT),
                    (184125, 186024, ABSENT),
                    (186025, 229999, PRESENT),
                ],
                padding=400,
            )
            started = time.perf_counter()
            report = analyze_commercial_edges(txt_path=txt, sidecar_path=sidecar, fps=25.0)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 30.0)
            self.assertEqual(report["proposals"][0]["proposed_end_frame"], 186024)


if __name__ == "__main__":
    unittest.main()
