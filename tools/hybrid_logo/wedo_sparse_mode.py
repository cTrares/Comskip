"""Experimental WeDo-only coarse discovery followed by local verification.

The released detector and other station profiles remain untouched. Only red
layout-confirmed intervals become internal cuts; raw logo misses merely open
search windows. The caller falls back to the released WeDo pipeline on failure.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from commercial_macro_mode import learn_macro_overlay_via_comskip
from internal_logo_sensor import read_frame_at
from public_broadcaster_fast_mode import probe_video
from video_frame_bounds import last_frame_seconds, sample_seconds_within_video
from wedo_movies_detector import (
    WedoMoviesConfig, _find_branded_bumper_cut, apply_wedo_movies_intervals,
    candidates_from_samples, cv2, is_layout_present, is_wedo_movies_video,
    layout_sample, np,
)

SAMPLE_SECONDS = 20
PRESENT_THRESHOLD = 0.42
MAX_LOCAL_COVERAGE = 0.60
PROCESSING_MODE = "wedo-sparse-local-v1"


def candidate_windows(observations: list[dict], duration: float) -> list[tuple[int, int]]:
    # Preserve even a single miss. Macro smoothing/90-second bridging must
    # never erase the shorter WeDo interruptions before layout verification.
    padding = math.ceil(WedoMoviesConfig().max_break_seconds + SAMPLE_SECONDS)
    windows: list[tuple[int, int]] = []
    for item in sorted(observations, key=lambda row: row["seconds"]):
        if item["logo_present"] and not item["red_layout"]:
            continue
        start = max(0, math.floor(item["seconds"] - padding))
        end = min(math.ceil(duration), math.ceil(item["seconds"] + padding))
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(end, windows[-1][1]))
        else:
            windows.append((start, end))
    return windows


def scan_layout_windows(video: Path, ffmpeg: Path, windows: list[tuple[int, int]],
                        duration: float, film_root: Path) -> dict:
    config = WedoMoviesConfig()
    positives = []
    measured = 0
    frame_bytes = config.analysis_width * config.analysis_height * 3
    for index, (start, end) in enumerate(windows):
        command = [
            str(ffmpeg), "-v", "error", "-ss", str(start), "-i", str(video),
            "-t", str(min(end, duration) - start), "-map", "0:v:0", "-an", "-sn", "-dn",
            "-vf", f"fps=1:start_time=0,scale={config.analysis_width}:{config.analysis_height}:flags=area",
            "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
        ]
        log_path = film_root / f"layout-{index}.log"
        # A file avoids blocking on a full stderr pipe during a decode error.
        with log_path.open("wb") as error_log:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            count = 0
            try:
                while True:
                    payload = process.stdout.read(frame_bytes)
                    if not payload:
                        break
                    if len(payload) != frame_bytes:
                        raise RuntimeError("Unvollständiges lokales WeDo-Analysebild")
                    frame = np.frombuffer(payload, dtype=np.uint8).reshape(
                        config.analysis_height, config.analysis_width, 3)
                    sample = layout_sample(frame, start + count, config)
                    if is_layout_present(sample, config):
                        positives.append(sample)
                    count += 1
                process.stdout.close()
                if process.wait() != 0:
                    raise RuntimeError(f"Lokaler WeDo-Decoder fehlgeschlagen: {log_path}")
                if count < math.floor(min(end, duration) - start) - 1:
                    raise RuntimeError("Lokaler WeDo-Decoder endete vor dem Fensterende")
                measured += count
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdout is not None:
                    process.stdout.close()
    candidates = candidates_from_samples(positives, duration_seconds=duration, config=config)
    return {
        "schema_version": PROCESSING_MODE,
        "status": "DETECTED" if candidates else "NO_BREAKS_FOUND",
        "activation": {"matched": True, "token": "wedo-movies"},
        "duration_seconds": duration,
        "candidates": [asdict(item) for item in candidates],
        "local_windows_seconds": windows,
        "layout_samples_measured": measured,
    }


def first_logo_return(score_at_times, start: float, end: float, fps: float,
                      *, total_frames: int | None = None) -> float | None:
    """One-second search, then frame resolution only in the first return bracket."""
    if total_frames is not None:
        end = min(end, last_frame_seconds(total_frames, fps))
    if start > end:
        return None
    previous = start
    times = list(range(math.ceil(start), math.floor(end) + 1))
    # Include a final fractional second, but never the exclusive video endpoint.
    if not times or times[-1] < end:
        times.append(end)
    for second in times:
        score = score_at_times([float(second)]).get(float(second))
        if score is None:
            raise RuntimeError("Logo-Messung in lokaler WeDo-Endprüfung fehlt")
        if score >= PRESENT_THRESHOLD:
            first = math.ceil(previous * fps - 1e-6)
            last = math.floor(second * fps + 1e-6)
            for frame in range(first, last + 1):
                seconds = frame / fps
                value = score_at_times([seconds]).get(seconds)
                if value is None:
                    raise RuntimeError("Logo-Messung an der WeDo-Schnittkante fehlt")
                if value >= PRESENT_THRESHOLD:
                    return seconds
            return float(second)
        previous = float(second)
    return None


def refine_tails(report: dict, video: Path, metadata, mask_path: Path, score_at_times) -> None:
    for candidate in report["candidates"]:
        original_end = candidate["end_seconds"]
        layout_end = candidate["last_layout_second"] + 1.0
        limit = min(metadata.duration_seconds, layout_end + 180.0)
        returned = first_logo_return(score_at_times, layout_end, limit, metadata.fps,
                                     total_frames=metadata.total_frames)
        # Missing return is ambiguous; let the caller use the established path.
        if returned is None:
            raise RuntimeError("Keine sichere Logo-Rückkehr im lokalen WeDo-Nachlauf")
        bumper = _find_branded_bumper_cut(
            video_path=video, fps=metadata.fps, earliest_seconds=original_end,
            logo_return_seconds=returned, logo_mask_path=mask_path,
        )
        end = bumper.commercial_end_frame / metadata.fps if bumper else returned
        video_end = min(metadata.duration_seconds, metadata.total_frames / metadata.fps)
        candidate["end_seconds"] = round(min(video_end, max(original_end, end)), 6)
        candidate["duration_seconds"] = round(candidate["end_seconds"] - candidate["start_seconds"], 6)
        candidate["program_hint_tail"] = {
            "normal_logo_return_seconds": returned,
            "original_end_seconds": original_end,
            "reason": "BRANDED_WEDO_BUMPER_TO_MOVIE_CUT" if bumper else "LOCAL_NORMAL_LOGO_RETURN",
            "logo_measurement": "comskip-mask-rect-python-reference",
        }


def outer_intervals(observations: list[dict], metadata, candidates: list[dict]) -> list[tuple[int, int]]:
    """Coarse physical-edge crops only; internal intervals always require red layout."""
    present = [row["seconds"] for row in observations if row["logo_present"] and not row["red_layout"]]
    if not present:
        raise RuntimeError("Kein verlässliches normales WeDo-Filmlogo")
    # Keep uncertain edge crops as one-frame navigation handles, not long cuts.
    start = min(present)
    end = min(metadata.duration_seconds, metadata.total_frames / metadata.fps,
              max(present) + SAMPLE_SECONDS)
    left = round(start * metadata.fps) if start <= 15 * 60 else 1
    right = round(end * metadata.fps) if metadata.duration_seconds - end <= 30 * 60 else metadata.total_frames
    proposed = [(1, max(1, left)), (max(1, right), metadata.total_frames)]
    internal = [(round(c["start_seconds"] * metadata.fps), round(c["end_seconds"] * metadata.fps))
                for c in candidates]
    return [edge for edge in proposed if not any(max(edge[0], a) <= min(edge[1], b) for a, b in internal)]


def run_wedo_sparse_mode(args, key: str, video: Path) -> dict:
    if not is_wedo_movies_video(video) or args.wedo_movies_mode != "active":
        raise ValueError("Der WeDo-Testscanner ist ausschließlich für aktives WeDo freigegeben")
    started = time.perf_counter()
    film_root = args.output_root / args.film_dirname
    film_root.mkdir(parents=True, exist_ok=True)
    metadata = probe_video(args.ffprobe, video)
    video_duration = min(metadata.duration_seconds, metadata.total_frames / metadata.fps)
    trace = getattr(args, "exit_trace", lambda *_a, **_kw: None)
    timings = {}
    capture = layout_capture = None
    try:
        print("[Phase 2/5] WeDo-Test: normales Senderlogo in fünf Ausschnitten lernen", flush=True)
        stage = time.perf_counter()
        capture, score_at_times, typical_score, learning = learn_macro_overlay_via_comskip(
            video=video, metadata=metadata, film_root=film_root, ffmpeg=args.ffmpeg,
            comskip=args.comskip, ini=args.ini,
        )
        if score_at_times is None or typical_score is None or typical_score < PRESENT_THRESHOLD:
            raise RuntimeError("Normales WeDo-Senderlogo nicht zuverlässig gelernt")
        timings["logo_learning"] = time.perf_counter() - stage
        print("[Phase 3/5] WeDo-Test: Logo und rotes Layout im 20-Sekunden-Raster prüfen", flush=True)
        stage = time.perf_counter()
        layout_capture = cv2.VideoCapture(str(video))
        config = WedoMoviesConfig()
        observations = []
        for second in sample_seconds_within_video(
                metadata.duration_seconds, metadata.total_frames, metadata.fps, SAMPLE_SECONDS):
            seconds = float(second)
            score = score_at_times([seconds]).get(seconds)
            frame = read_frame_at(layout_capture, seconds)
            if score is None or frame is None:
                raise RuntimeError(f"Unvollständige WeDo-Stichprobe bei {seconds} Sekunden")
            small = cv2.resize(frame, (config.analysis_width, config.analysis_height), interpolation=cv2.INTER_AREA)
            red = is_layout_present(layout_sample(small, int(second), config), config)
            observations.append({"seconds": seconds, "logo_score": score,
                                 "logo_present": score >= PRESENT_THRESHOLD, "red_layout": red})
        windows = candidate_windows(observations, video_duration)
        coverage = sum(min(end, video_duration) - start for start, end in windows) / video_duration
        timings["coarse_scan"] = time.perf_counter() - stage
        trace("WEDO_SPARSE_DISCOVERY", samples=len(observations), windows=windows, coverage=coverage)
        if not windows or coverage > MAX_LOCAL_COVERAGE:
            raise RuntimeError("WeDo-Stichproben ergeben keine ausreichend eingegrenzten Suchfenster")
        print(f"[Phase 4/5] WeDo-Test: {len(windows)} Verdachtsbereiche lokal prüfen", flush=True)
        stage = time.perf_counter()
        report = scan_layout_windows(video, args.ffmpeg, windows, video_duration, film_root)
        timings["local_layout_scan"] = time.perf_counter() - stage
        if not report["candidates"]:
            raise RuntimeError("Keine bestätigten roten WeDo-Blöcke im lokalen Scan")
        stage = time.perf_counter()
        refine_tails(report, video, metadata, film_root / "selected.logo.txt", score_at_times)
        timings["local_tail_refinement"] = time.perf_counter() - stage
        print("[Phase 5/5] WeDo-Test: bestätigte Blöcke ausgeben", flush=True)
        final_root = film_root / "final"
        final_root.mkdir(exist_ok=True)
        txt, edl = final_root / "final.txt", final_root / "final.edl"
        edges = outer_intervals(observations, metadata, report["candidates"])
        txt.write_text(
            f"FILE PROCESSING COMPLETE {metadata.total_frames} FRAMES AT {round(metadata.fps * 100):5d}\n"
            "-------------------\n" + "".join(f"{a}\t{b}\n" for a, b in edges), encoding="ascii")
        edl.write_text("", encoding="ascii")
        fusion = apply_wedo_movies_intervals(txt_path=txt, edl_path=edl, report=report,
                                            fps=metadata.fps, authoritative=True)
        timings["total"] = time.perf_counter() - started
        result = {
            "schema_version": PROCESSING_MODE, "processing_mode": PROCESSING_MODE,
            "video_metadata": asdict(metadata), "final_stage_intervals": fusion["fused_intervals"],
            "runtime_seconds": timings, "logo_learning": learning,
            "coarse_sample_seconds": SAMPLE_SECONDS, "coarse_observations": observations,
            "last_valid_sample_seconds": last_frame_seconds(metadata.total_frames, metadata.fps),
            "local_coverage": coverage, "outer_crops": "coarse-logo-edge-markers",
            "wedo_movies": {"mode": "active", "report": report, "fusion": fusion},
        }
        (film_root / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        (final_root / "final.log").write_text(
            "WEDO TEST: sparse-local-v1\n"
            f"Stichproben: {len(observations)}; lokale Fenster: {len(windows)}; Abdeckung: {coverage:.1%}\n"
            f"Bestaetigte rote Bloecke: {len(report['candidates'])}\n"
            "Dateiraender: grobe Logo-Marker, manuell pruefen.\n"
            + json.dumps(timings, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if capture is not None:
            capture.release()
        if layout_capture is not None:
            layout_capture.release()


def run_wedo_with_fallback(args, key: str, video: Path, legacy_runner) -> dict:
    started = time.perf_counter()
    try:
        return run_wedo_sparse_mode(args, key, video)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        print(f"WeDo-Test: Rückfall auf bisherigen WeDo-Weg ({reason})", flush=True)
        film_root = args.output_root / args.film_dirname
        if film_root.exists():
            # Keep the failed attempt for diagnostics, outside the legacy run directory.
            film_root.rename(args.output_root / "wedo-sparse-attempt")
        result = legacy_runner(args, key, video)
        result["wedo_sparse_fallback"] = {"reason": reason}
        result["runtime_seconds"]["including_sparse_attempt"] = time.perf_counter() - started
        (film_root / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        with (film_root / "final" / "final.log").open("a", encoding="utf-8") as log:
            log.write(f"\nWEDO SPARSE FALLBACK: {reason}\n")
        return result
