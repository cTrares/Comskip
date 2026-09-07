"""Native v1 logo observations from lossless, bounded WeDo tail clips."""
from __future__ import annotations

import csv
import json
import math
import os
import subprocess
from pathlib import Path

from video_frame_bounds import last_frame_seconds

CONTEXT_SECONDS = 30
MAX_TAIL_SECONDS = 180


def tail_window(layout_end: float, metadata) -> tuple[float, float]:
    # Native Comskip samples every int(fps) frames with the shipped INI.
    # Whole-second starts preserve that phase for the recordings supported here.
    # A different cadence uses the complete legacy run instead of shifted cuts.
    if not math.isclose(metadata.fps, round(metadata.fps), abs_tol=1e-6):
        raise RuntimeError("Lokale native WeDo-Endprüfung benötigt ganzzahlige Bildrate")
    if layout_end > last_frame_seconds(metadata.total_frames, metadata.fps):
        raise RuntimeError("Kein Videobild nach dem roten WeDo-Layout")
    return (float(max(0, math.floor(layout_end - CONTEXT_SECONDS))),
            min(metadata.duration_seconds, metadata.total_frames / metadata.fps,
                math.ceil(layout_end + MAX_TAIL_SECONDS + CONTEXT_SECONDS)))


def run_logged(command: list[str], log: Path, accepted=(0,)) -> None:
    with log.open("wb") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode not in accepted:
        raise RuntimeError(f"Native WeDo-Endprüfung fehlgeschlagen: {log}")


def native_sidecar(raw: Path, sidecar: Path, start: float, end: float, fps: float) -> int:
    """Translate native states, never the Python reference score, to v1 input."""
    count = 0
    previous = None
    with raw.open(newline="", encoding="utf-8-sig") as source, sidecar.open("w", encoding="utf-8") as target:
        target.write(json.dumps({"record_type": "metadata",
                                 "global_reliability": {"comskip": "LOCAL_NATIVE_ENABLED"},
                                 "measurement_scope_seconds": [start, end]}) + "\n")
        for row in csv.DictReader(source):
            seconds = float(row["time_seconds"])
            frame = int(row["frame"])
            if (not math.isfinite(seconds) or int(row["comskip_present"]) not in (0, 1)
                    or int(row["global_logo_enabled"]) != 1
                    or frame != count + 1
                    or (previous is None and abs(seconds) > 1 / fps)
                    or (previous is not None and not 0 < seconds - previous <= 1.5 / fps)
                    or seconds < 0 or start + seconds >= end + 1e-6):
                raise RuntimeError("Unvollständige oder ungültige native WeDo-Logo-Messung")
            target.write(json.dumps({
                "record_type": "observation", "time_seconds": round(start + seconds, 6),
                "comskip_frame": round(start * fps) + frame,
                "comskip_local_state": "PRESENT" if int(row["comskip_present"]) else "ABSENT",
            }) + "\n")
            previous = seconds
            count += 1
    # Native raw output omits its final frame. Allow a few decoder boundary frames,
    # but reject a truncated clip even when an early, apparently valid return exists.
    if previous is None or start + previous < end - 4 / fps:
        raise RuntimeError("Native WeDo-Logo-Messung endet vor dem lokalen Fensterende")
    return count


def measure_tail(*, video: Path, metadata, layout_end: float, mask: Path,
                 ffmpeg: Path, comskip: Path, ini: Path, output: Path) -> tuple[Path, dict]:
    start, end = tail_window(layout_end, metadata)
    output.mkdir(parents=True, exist_ok=True)
    clip = output / "tail.mp4"
    sidecar = output / "native-logo.jsonl"
    # Decode-accurate input seeking and lossless encoding retain the original
    # resolution and luma edges. Stream copying would move the start to a keyframe.
    extract = [str(ffmpeg), "-v", "error", "-y", "-ss", str(start), "-i", str(video),
               "-t", str(end - start), "-map", "0:v:0", "-an", "-sn", "-dn",
               "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0",
               "-fps_mode", "passthrough", str(clip)]
    native = [str(comskip), "--ini", str(ini), "--output", str(output),
              "--output-filename", "native", "--logo", str(mask), "--logo-raw", str(clip)]
    try:
        run_logged(extract, output / "extract.log")
        run_logged(native, output / "native-run.log", accepted=(0, 1))
        count = native_sidecar(output / "native.logo-raw.csv", sidecar, start, end, metadata.fps)
    finally:
        # Only the disposable clip is removed; raw measurements and logs remain.
        clip.unlink(missing_ok=True)
    return sidecar, {"logo_measurement": "comskip-native-v1-local",
                     "window_seconds": [start, end], "observations": count,
                     "native_raw": str(output / "native.logo-raw.csv"),
                     "context_seconds": CONTEXT_SECONDS}
