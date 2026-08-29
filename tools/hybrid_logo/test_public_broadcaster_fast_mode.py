from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from public_broadcaster_fast_mode import (
    BlackInterval,
    BoundaryCandidate,
    VideoMetadata,
    channel_from_filename,
    choose_boundary_candidate,
    load_fast_mode_channels,
    parse_black_intervals,
    selected_fast_mode_channel,
    write_fast_outputs,
)


class PublicBroadcasterFastModeTests(unittest.TestCase):
    def test_configuration_ignores_documentation_and_supports_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Schnellmodus-Sender.txt"
            path.write_text("# Erklärung\n\narte\nZDF-Neo\n# zdf\n", encoding="utf-8")
            self.assertEqual(load_fast_mode_channels(path), {"arte", "zdf-neo"})

    def test_channel_matching_is_exact(self) -> None:
        arte = Path("2026-08-23_20-15_Film_arte_hd.mp4")
        zdf_neo = Path("2026-08-23_20-15_Film_zdf_neo_hd.mp4")
        self.assertEqual(channel_from_filename(arte), "arte")
        self.assertEqual(selected_fast_mode_channel(arte, {"arte"}), "arte")
        self.assertIsNone(selected_fast_mode_channel(zdf_neo, {"zdf"}))
        self.assertEqual(selected_fast_mode_channel(zdf_neo, {"zdfneo"}), "zdfneo")

    def test_blackdetect_timestamps_receive_seek_offset(self) -> None:
        parsed = parse_black_intervals(
            "black_start:10.5 black_end:11.25 black_duration:0.75",
            offset_seconds=100.0,
        )
        self.assertEqual(parsed, [BlackInterval(110.5, 111.25, 0.75)])

    def test_directional_overlay_change_selects_program_boundary(self) -> None:
        intervals = [
            BlackInterval(100.0, 101.0, 1.0),
            BlackInterval(300.0, 301.0, 1.0),
        ]
        scores = {
            75.0: 0.8,
            90.0: 0.8,
            111.0: 0.8,
            126.0: 0.8,
            275.0: 0.2,
            290.0: 0.2,
            311.0: 0.8,
            326.0: 0.8,
        }
        selected, _evaluated = choose_boundary_candidate(
            intervals,
            side="start",
            duration_seconds=1000.0,
            score_at_times=lambda times: {time: scores[time] for time in times},
            central_score=0.8,
        )
        self.assertAlmostEqual(selected.seconds, 300.0)

    def test_black_at_physical_file_edge_uses_its_inner_edge(self) -> None:
        start, _ = choose_boundary_candidate(
            [BlackInterval(0.0, 10.0, 10.0)],
            side="start",
            duration_seconds=60.0,
            score_at_times=None,
            central_score=None,
        )
        end, _ = choose_boundary_candidate(
            [BlackInterval(50.0, 60.0, 10.0)],
            side="end",
            duration_seconds=60.0,
            score_at_times=None,
            central_score=None,
        )
        self.assertEqual(start.seconds, 10.0)
        self.assertEqual(end.seconds, 50.0)

    def test_output_always_contains_two_editable_edge_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = write_fast_outputs(
                film_root=root,
                metadata=VideoMetadata(100.0, 25.0, 2500, 1280, 720),
                channel="arte",
                config_path=root / "Schnellmodus-Sender.txt",
                start=BoundaryCandidate(10.0, 9.8, 10.2, 0.4, 0.2, 0.8, 0.6, 1.0),
                end=BoundaryCandidate(90.0, 89.8, 90.2, 0.4, 0.8, 0.2, 0.6, 1.0),
                details={},
                runtime_seconds=2.0,
            )
            lines = (root / "final" / "final.txt").read_text(encoding="ascii").splitlines()
            self.assertEqual(lines[2], "1\t251")
            self.assertEqual(lines[3], "2251\t2500")
            self.assertEqual(result["processing_mode"], "fast-boundary")
            self.assertTrue((root / "fast-mode-marker.txt").is_file())


if __name__ == "__main__":
    unittest.main()
