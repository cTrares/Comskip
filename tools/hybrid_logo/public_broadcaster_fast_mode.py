from __future__ import annotations

import json
import math
import os
import re
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path


CONFIG_NAME = "Schnellmodus-Sender.txt"
MARKER_NAME = "fast-mode-marker.txt"
PROCESSING_MODE = "fast-boundary"
DEFAULT_TIME_BUDGET_SECONDS = 55.0
START_SEARCH_SECONDS = 15 * 60.0
END_SEARCH_SECONDS = 30 * 60.0
NEIGHBOURING_TRANSITION_SECONDS = 90.0
NEIGHBOURING_SCORE_FRACTION = 0.75
BLACK_RE = re.compile(
    r"black_start:(?P<start>[0-9.]+)\s+black_end:(?P<end>[0-9.]+)\s+"
    r"black_duration:(?P<duration>[0-9.]+)"
)


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    fps: float
    total_frames: int
    width: int
    height: int


@dataclass(frozen=True)
class BlackInterval:
    start_seconds: float
    end_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class BoundaryCandidate:
    seconds: float
    black_start_seconds: float
    black_end_seconds: float
    black_duration_seconds: float
    before_score: float | None
    after_score: float | None
    directional_change: float | None
    selection_score: float


def load_fast_mode_channels(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    channels: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        token = line.casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", token):
            raise ValueError(f"Ungültiger Sender-Token in {path.name}: {line!r}")
        channels.add(token)
    return channels


def channel_from_filename(video: Path) -> str | None:
    match = re.search(r"_([^_]+)_(?:hd|hq)$", video.stem.casefold())
    return match.group(1) if match else None


def _channel_filename_aliases(channel: str) -> set[str]:
    compact = channel.replace("-", "").replace("_", "")
    aliases = {channel, compact}
    if compact == "zdfneo":
        aliases.update({"zdf-neo", "zdf_neo"})
    return aliases


def selected_fast_mode_channel(video: Path, channels: set[str]) -> str | None:
    stem = video.stem.casefold()
    for channel in sorted(channels, key=len, reverse=True):
        if any(stem.endswith(f"_{alias}_hd") or stem.endswith(f"_{alias}_hq")
               for alias in _channel_filename_aliases(channel)):
            return channel
    return None


def probe_video(ffprobe: Path, video: Path) -> VideoMetadata:
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate,nb_frames,width,height:format=duration",
        "-of",
        "json",
        str(video),
    ]
    payload = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))
    stream = payload["streams"][0]
    numerator, denominator = stream["avg_frame_rate"].split("/", 1)
    fps = float(numerator) / float(denominator)
    duration = float(payload["format"]["duration"])
    total_frames = int(stream.get("nb_frames") or round(duration * fps))
    if fps <= 0 or duration <= 0 or total_frames < 3:
        raise RuntimeError(f"Ungültige Videometadaten für {video}")
    return VideoMetadata(
        duration_seconds=duration,
        fps=fps,
        total_frames=total_frames,
        width=int(stream["width"]),
        height=int(stream["height"]),
    )


def parse_black_intervals(output: str, *, offset_seconds: float) -> list[BlackInterval]:
    intervals = []
    for match in BLACK_RE.finditer(output):
        start = offset_seconds + float(match.group("start"))
        end = offset_seconds + float(match.group("end"))
        intervals.append(BlackInterval(start, end, max(0.0, end - start)))
    return intervals


def scan_black_intervals(
    *,
    ffmpeg: Path,
    video: Path,
    offset_seconds: float,
    duration_seconds: float,
    deadline: float,
) -> tuple[list[BlackInterval], dict]:
    started = time.perf_counter()
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "info",
        "-ss",
        f"{offset_seconds:.6f}",
        "-t",
        f"{duration_seconds:.6f}",
        "-skip_frame",
        "noref",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        "scale=160:-2,blackdetect=d=0.04:pix_th=0.12",
        "-f",
        "null",
        "NUL" if os.name == "nt" else "/dev/null",
    ]
    timeout = max(1.0, deadline - time.perf_counter())
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
            creationflags=creationflags,
        )
        output = completed.stdout
        status = "OK" if completed.returncode == 0 else f"EXIT_{completed.returncode}"
    except subprocess.TimeoutExpired as exc:
        chunks = []
        for chunk in (exc.stdout, exc.stderr):
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode("utf-8", errors="replace"))
            elif chunk:
                chunks.append(chunk)
        output = "".join(chunks)
        status = "TIME_BUDGET_EXCEEDED"
    intervals = parse_black_intervals(output, offset_seconds=offset_seconds)
    return intervals, {
        "status": status,
        "offset_seconds": offset_seconds,
        "duration_seconds": duration_seconds,
        "interval_count": len(intervals),
        "runtime_seconds": time.perf_counter() - started,
    }


def reduce_black_candidates(intervals: list[BlackInterval]) -> list[BlackInterval]:
    unique = {
        (round(item.start_seconds, 6), round(item.end_seconds, 6)): item
        for item in intervals
    }
    return sorted(unique.values(), key=lambda item: item.start_seconds)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _position_prior(seconds: float, *, side: str, duration_seconds: float) -> float:
    if side == "start":
        center, spread = 6.0 * 60.0, 6.0 * 60.0
        distance = abs(seconds - center)
    else:
        center, spread = 12.0 * 60.0, 12.0 * 60.0
        distance = abs((duration_seconds - seconds) - center)
    return math.exp(-0.5 * (distance / spread) ** 2)


def choose_boundary_candidate(
    intervals: list[BlackInterval],
    *,
    side: str,
    duration_seconds: float,
    score_at_times,
    central_score: float | None,
) -> tuple[BoundaryCandidate, list[BoundaryCandidate]]:
    candidates = reduce_black_candidates(intervals)
    if not candidates:
        fallback = 6.0 * 60.0 if side == "start" else duration_seconds - 12.0 * 60.0
        fallback = max(1.0, min(duration_seconds - 1.0, fallback))
        candidate = BoundaryCandidate(fallback, fallback, fallback, 0.0, None, None, None, 0.0)
        return candidate, [candidate]

    times: set[float] = set()
    sample_times: dict[tuple[float, float], tuple[list[float], list[float]]] = {}
    for interval in candidates:
        before = [max(0.0, interval.start_seconds - delta) for delta in (25.0, 10.0)]
        after = [min(duration_seconds, interval.end_seconds + delta) for delta in (10.0, 25.0)]
        sample_times[(interval.start_seconds, interval.end_seconds)] = (before, after)
        times.update(before)
        times.update(after)
    scores = score_at_times(sorted(times)) if score_at_times is not None else {}
    reference = max(0.20, central_score or 0.42)
    evaluated = []
    for interval in candidates:
        before_times, after_times = sample_times[(interval.start_seconds, interval.end_seconds)]
        before = _median([scores[t] for t in before_times if t in scores])
        after = _median([scores[t] for t in after_times if t in scores])
        if before is None or after is None:
            change = None
            directional = 0.0
            support = 0.0
        else:
            change = (after - before) if side == "start" else (before - after)
            directional = change / reference
            inside = after if side == "start" else before
            outside = before if side == "start" else after
            support = (inside - outside) / reference
        black_strength = min(1.0, interval.duration_seconds / 2.0)
        prior = _position_prior(interval.start_seconds, side=side, duration_seconds=duration_seconds)
        selection = directional * 3.0 + support * 1.2 + black_strength * 0.35 + prior * 0.30
        edge_margin = min(30.0, duration_seconds * 0.05)
        if side == "start":
            point = (
                interval.end_seconds
                if interval.start_seconds < edge_margin
                else interval.start_seconds
            )
        else:
            point = (
                interval.start_seconds
                if interval.end_seconds > duration_seconds - edge_margin
                else interval.end_seconds
            )
        evaluated.append(
            BoundaryCandidate(
                seconds=point,
                black_start_seconds=interval.start_seconds,
                black_end_seconds=interval.end_seconds,
                black_duration_seconds=interval.duration_seconds,
                before_score=before,
                after_score=after,
                directional_change=change,
                selection_score=selection,
            )
        )
    evaluated.sort(key=lambda item: item.selection_score, reverse=True)
    strongest = evaluated[0]
    neighbouring_earlier = [
        item
        for item in evaluated
        if strongest.seconds - NEIGHBOURING_TRANSITION_SECONDS <= item.seconds <= strongest.seconds
        and item.selection_score >= strongest.selection_score * NEIGHBOURING_SCORE_FRACTION
    ]
    selected = min(neighbouring_earlier, key=lambda item: item.seconds)
    return selected, evaluated


def learn_dynamic_overlay(video: Path, metadata: VideoMetadata):
    from hybrid_logo_analysis import learn_overlay_in_range, load_internal_logo_api

    api = load_internal_logo_api()
    (
        cv2,
        np,
        ProgramOverlay,
        OverlayReference,
        detect_logo_by_heatmap,
        read_frame_at,
        crop_rect,
        normalize_gray,
        edge_image,
        build_template_mask,
        overlay_present_score,
        _overlay_present_score_from_crop,
    ) = api
    learned = learn_overlay_in_range(
        video=video,
        start_seconds=metadata.duration_seconds * 0.40,
        end_seconds=metadata.duration_seconds * 0.60,
        heatmap_samples=24,
        reference_samples=12,
        cv2=cv2,
        np=np,
        ProgramOverlay=ProgramOverlay,
        OverlayReference=OverlayReference,
        detect_logo_by_heatmap=detect_logo_by_heatmap,
        read_frame_at=read_frame_at,
        crop_rect=crop_rect,
        normalize_gray=normalize_gray,
        edge_image=edge_image,
        build_template_mask=build_template_mask,
    )
    overlay, reference = learned[0], learned[1]
    if reference is None:
        return None, None, None, {"status": "NO_DYNAMIC_OVERLAY"}

    capture = cv2.VideoCapture(str(video))
    cache: dict[float, float] = {}

    def score_at_times(times: list[float]) -> dict[float, float]:
        for seconds in sorted(set(times)):
            if seconds in cache:
                continue
            frame = read_frame_at(capture, seconds)
            if frame is not None:
                cache[seconds] = float(overlay_present_score(reference, frame))
        return {seconds: cache[seconds] for seconds in times if seconds in cache}

    central_times = [
        metadata.duration_seconds * fraction
        for fraction in (0.42, 0.46, 0.50, 0.54, 0.58)
    ]
    central_scores = list(score_at_times(central_times).values())
    central_score = _median(central_scores)
    detail = {
        "status": "DYNAMIC_OVERLAY_LEARNED",
        "source": overlay.source,
        "rect_discovered_for_this_recording": list(overlay.rect),
        "confidence": overlay.confidence,
        "sample_count": overlay.sample_count,
        "central_score": central_score,
    }
    return capture, score_at_times, central_score, detail


def frame_for_seconds(seconds: float, *, fps: float, total_frames: int) -> int:
    return max(1, min(total_frames, int(round(seconds * fps)) + 1))


def write_fast_outputs(
    *,
    film_root: Path,
    metadata: VideoMetadata,
    channel: str,
    config_path: Path,
    start: BoundaryCandidate,
    end: BoundaryCandidate,
    details: dict,
    runtime_seconds: float,
) -> dict:
    final_root = film_root / "final"
    final_root.mkdir(parents=True, exist_ok=True)
    start_frame = frame_for_seconds(start.seconds, fps=metadata.fps, total_frames=metadata.total_frames)
    end_frame = frame_for_seconds(end.seconds, fps=metadata.fps, total_frames=metadata.total_frames)
    start_frame = max(2, min(start_frame, metadata.total_frames - 2))
    end_frame = max(start_frame + 1, min(end_frame, metadata.total_frames - 1))
    intervals = [(1, start_frame), (end_frame, metadata.total_frames)]
    rate100 = int(round(metadata.fps * 100))
    txt = (
        f"FILE PROCESSING COMPLETE {metadata.total_frames} FRAMES AT {rate100:5d}\n"
        "-------------------\n"
        + "".join(f"{left}\t{right}\n" for left, right in intervals)
    )
    edl = "".join(
        f"{max(left - 1, 0) / metadata.fps:.2f}\t"
        f"{max(right - 1, 0) / metadata.fps:.2f}\t0\n"
        for left, right in intervals
    )
    marker = (
        "SCHNELLMODUS AKTIV\n"
        f"Sender: {channel}\n"
        "Verarbeitung: nur grobe Randblöcke, keine inneren Werbeblöcke\n"
        f"Erster Randblock: Frame 1 bis {start_frame}\n"
        f"Letzter Randblock: Frame {end_frame} bis {metadata.total_frames}\n"
        "Korrektur in ComskipGUI: Filmanfang suchen und E drücken; Filmende suchen und B drücken.\n"
    )
    log = (
        "=" * 72
        + "\nSCHNELLMODUS AKTIV\n"
        + f"Sender: {channel}\n"
        + f"Senderliste: {config_path}\n"
        + "Keine Suche nach inneren Werbeblöcken.\n"
        + f"Geschätzter Filmanfang: {start.seconds:.3f} s / Frame {start_frame}\n"
        + f"Geschätztes Filmende: {end.seconds:.3f} s / Frame {end_frame}\n"
        + f"Laufzeit: {runtime_seconds:.3f} s\n"
        + "=" * 72
        + "\n"
    )
    (final_root / "final.txt").write_text(txt, encoding="ascii", newline="\n")
    (final_root / "final.edl").write_text(edl, encoding="ascii", newline="\n")
    (final_root / "final.log").write_text(log, encoding="utf-8", newline="\n")
    (film_root / MARKER_NAME).write_text(marker, encoding="utf-8", newline="\n")
    result = {
        "schema_version": "public-broadcaster-fast-boundary-v1",
        "processing_mode": PROCESSING_MODE,
        "fast_mode": True,
        "detected_channel": channel,
        "channel_list": str(config_path),
        "internal_commercial_scan": False,
        "video_metadata": asdict(metadata),
        "estimated_boundaries_seconds": {
            "film_start": start.seconds,
            "film_end": end.seconds,
        },
        "final_stage_intervals": [list(interval) for interval in intervals],
        "boundary_candidates": {
            "start": asdict(start),
            "end": asdict(end),
        },
        "analysis": details,
        "runtime_seconds": {"total": runtime_seconds},
        "outputs": {
            "final_stage_txt": str(final_root / "final.txt"),
            "fast_mode_marker": str(film_root / MARKER_NAME),
        },
    }
    (film_root / "diagnostic.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_public_broadcaster_fast_mode(
    *,
    video: Path,
    film_root: Path,
    ffmpeg: Path,
    ffprobe: Path,
    channel: str,
    config_path: Path,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
) -> dict:
    started = time.perf_counter()
    deadline = started + time_budget_seconds
    metadata = probe_video(ffprobe, video)
    start_duration = min(START_SEARCH_SECONDS, metadata.duration_seconds * 0.45)
    end_offset = max(metadata.duration_seconds * 0.55, metadata.duration_seconds - END_SEARCH_SECONDS)
    end_duration = metadata.duration_seconds - end_offset

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="fast-boundary") as executor:
        overlay_future = executor.submit(learn_dynamic_overlay, video, metadata)
        start_future = executor.submit(
            scan_black_intervals,
            ffmpeg=ffmpeg,
            video=video,
            offset_seconds=0.0,
            duration_seconds=start_duration,
            deadline=deadline,
        )
        end_future = executor.submit(
            scan_black_intervals,
            ffmpeg=ffmpeg,
            video=video,
            offset_seconds=end_offset,
            duration_seconds=end_duration,
            deadline=deadline,
        )
        try:
            capture, score_at_times, central_score, overlay_detail = overlay_future.result()
        except Exception as exc:
            capture, score_at_times, central_score = None, None, None
            overlay_detail = {
                "status": "DYNAMIC_OVERLAY_FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        start_intervals, start_scan = start_future.result()
        end_intervals, end_scan = end_future.result()

    scoring_enabled = deadline - time.perf_counter() >= 8.0
    scorer = score_at_times if scoring_enabled else None
    try:
        start, start_candidates = choose_boundary_candidate(
            start_intervals,
            side="start",
            duration_seconds=metadata.duration_seconds,
            score_at_times=scorer,
            central_score=central_score,
        )
        end, end_candidates = choose_boundary_candidate(
            end_intervals,
            side="end",
            duration_seconds=metadata.duration_seconds,
            score_at_times=scorer,
            central_score=central_score,
        )
    finally:
        if capture is not None:
            capture.release()

    runtime = time.perf_counter() - started
    detail = {
        "strategy": "middle_anchor_dynamic_overlay_plus_reduced_reference_black_transitions",
        "time_budget_seconds": time_budget_seconds,
        "time_budget_exceeded": runtime > time_budget_seconds,
        "dynamic_scoring_enabled": scoring_enabled,
        "dynamic_overlay": overlay_detail,
        "black_scans": {"start": start_scan, "end": end_scan},
        "candidate_counts": {
            "start_raw": len(start_intervals),
            "start_scored": len(start_candidates),
            "end_raw": len(end_intervals),
            "end_scored": len(end_candidates),
        },
        "top_start_candidates": [asdict(item) for item in start_candidates[:5]],
        "top_end_candidates": [asdict(item) for item in end_candidates[:5]],
    }
    return write_fast_outputs(
        film_root=film_root,
        metadata=metadata,
        channel=channel,
        config_path=config_path,
        start=start,
        end=end,
        details=detail,
        runtime_seconds=runtime,
    )
