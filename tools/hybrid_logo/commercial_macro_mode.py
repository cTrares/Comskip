from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from public_broadcaster_fast_mode import (
    VideoMetadata,
    frame_for_seconds,
    probe_video,
    selected_fast_mode_channel,
)


CONFIG_NAME = "Makromodus-Sender.txt"
MARKER_NAME = "macro-mode-marker.txt"
PROCESSING_MODE = "commercial-logo-macro"
DEFAULT_TIME_BUDGET_SECONDS = 55.0
DEFAULT_SAMPLE_SECONDS = 20.0
DEFAULT_PRESENT_THRESHOLD = 0.42
DEFAULT_MIN_FILM_RUN_SECONDS = 6.0 * 60.0
DEFAULT_MIN_BREAK_SECONDS = 90.0
DEFAULT_BRIDGE_SECONDS = 45.0
LOCAL_STEP_SECONDS = 2.0
LOCAL_RADIUS_SECONDS = 40.0
LOCAL_PERSISTENCE = 3
LEARNING_EDGE_GUARD_SECONDS = 6.0 * 60.0


@dataclass(frozen=True)
class MacroSample:
    seconds: float
    score: float
    present: bool


@dataclass(frozen=True)
class MacroRun:
    start_seconds: float
    end_seconds: float
    present: bool
    sample_count: int
    median_score: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def load_macro_channels(path: Path) -> set[str]:
    # The public fast-mode parser already provides the exact, comment-friendly
    # filename token format required by both station lists.
    from public_broadcaster_fast_mode import load_fast_mode_channels

    return load_fast_mode_channels(path)


def selected_macro_channel(video: Path, channels: set[str]) -> str | None:
    return selected_fast_mode_channel(video, channels)


def learn_macro_overlay(video: Path, metadata: VideoMetadata):
    """Learn one recording-local logo from samples spread across the program."""
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
    guard = min(LEARNING_EDGE_GUARD_SECONDS, metadata.duration_seconds * 0.12)
    learned = learn_overlay_in_range(
        video=video,
        start_seconds=guard,
        end_seconds=metadata.duration_seconds - guard,
        heatmap_samples=48,
        reference_samples=24,
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
        return None, None, None, {"status": "NO_DISTRIBUTED_DYNAMIC_OVERLAY"}

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

    reference_times = [
        guard + (metadata.duration_seconds - 2.0 * guard) * index / 10.0
        for index in range(11)
    ]
    reference_scores = list(score_at_times(reference_times).values())
    typical_score = statistics.median(reference_scores) if reference_scores else None
    detail = {
        "status": "DISTRIBUTED_DYNAMIC_OVERLAY_LEARNED",
        "source": overlay.source,
        "rect_discovered_for_this_recording": list(overlay.rect),
        "confidence": overlay.confidence,
        "sample_count": overlay.sample_count,
        "learning_range_seconds": [guard, metadata.duration_seconds - guard],
        "typical_distributed_score": typical_score,
    }
    return capture, score_at_times, typical_score, detail


def progressive_sample_stages(duration_seconds: float, sample_seconds: float) -> list[list[float]]:
    """Cover the complete recording coarsely before filling the gaps."""
    if duration_seconds <= 0 or sample_seconds <= 0:
        return []
    count = max(2, int(duration_seconds // sample_seconds) + 1)
    grid = [min(duration_seconds, index * sample_seconds) for index in range(count)]
    if grid[-1] < duration_seconds:
        grid.append(duration_seconds)
    indices = list(range(len(grid)))
    stages = [
        [grid[index] for index in indices if index % 4 == 0],
        [grid[index] for index in indices if index % 4 == 2],
        [grid[index] for index in indices if index % 2 == 1],
    ]
    stages[0].append(grid[-1])
    seen: set[float] = set()
    result = []
    for stage in stages:
        unique = []
        for seconds in sorted(stage):
            value = round(seconds, 6)
            if value not in seen:
                seen.add(value)
                unique.append(value)
        if unique:
            result.append(unique)
    return result


def _median_states(samples: list[MacroSample], radius: int = 1) -> list[MacroSample]:
    smoothed = []
    for index, sample in enumerate(samples):
        window = samples[max(0, index - radius): index + radius + 1]
        score = float(statistics.median(item.score for item in window))
        smoothed.append(MacroSample(sample.seconds, score, score >= DEFAULT_PRESENT_THRESHOLD))
    return smoothed


def _raw_runs(samples: list[MacroSample], duration_seconds: float) -> list[MacroRun]:
    if not samples:
        return []
    ordered = sorted(samples, key=lambda item: item.seconds)
    nominal_step = statistics.median(
        right.seconds - left.seconds for left, right in zip(ordered, ordered[1:])
    ) if len(ordered) > 1 else duration_seconds
    runs = []
    start = 0
    for index in range(1, len(ordered) + 1):
        if index < len(ordered) and ordered[index].present == ordered[start].present:
            continue
        segment = ordered[start:index]
        left = max(0.0, segment[0].seconds - nominal_step / 2.0)
        right = min(duration_seconds, segment[-1].seconds + nominal_step / 2.0)
        runs.append(
            MacroRun(
                start_seconds=left,
                end_seconds=max(left, right),
                present=segment[0].present,
                sample_count=len(segment),
                median_score=float(statistics.median(item.score for item in segment)),
            )
        )
        start = index
    return runs


def build_film_runs(
    samples: list[MacroSample],
    *,
    duration_seconds: float,
    min_film_run_seconds: float = DEFAULT_MIN_FILM_RUN_SECONDS,
    min_break_seconds: float = DEFAULT_MIN_BREAK_SECONDS,
    bridge_seconds: float = DEFAULT_BRIDGE_SECONDS,
) -> tuple[list[MacroRun], list[MacroRun]]:
    """Return all state runs and the long, merged program-logo anchors."""
    runs = _raw_runs(_median_states(sorted(samples, key=lambda item: item.seconds)), duration_seconds)
    anchors = [run for run in runs if run.present and run.duration_seconds >= min_film_run_seconds]
    if not anchors:
        present_runs = [run for run in runs if run.present]
        if present_runs:
            longest = max(present_runs, key=lambda item: item.duration_seconds)
            if longest.duration_seconds >= min_film_run_seconds / 2.0:
                anchors = [longest]
    merged: list[MacroRun] = []
    for anchor in anchors:
        if merged and anchor.start_seconds - merged[-1].end_seconds < max(min_break_seconds, bridge_seconds):
            previous = merged.pop()
            merged.append(
                MacroRun(
                    previous.start_seconds,
                    anchor.end_seconds,
                    True,
                    previous.sample_count + anchor.sample_count,
                    (previous.median_score + anchor.median_score) / 2.0,
                )
            )
        else:
            merged.append(anchor)
    return runs, merged


def intervals_from_film_runs(
    film_runs: list[MacroRun],
    *,
    duration_seconds: float,
    min_break_seconds: float = DEFAULT_MIN_BREAK_SECONDS,
) -> list[tuple[float, float]]:
    if not film_runs:
        return []
    intervals: list[tuple[float, float]] = []
    if film_runs[0].start_seconds >= 20.0:
        intervals.append((0.0, film_runs[0].start_seconds))
    for left, right in zip(film_runs, film_runs[1:]):
        if right.start_seconds - left.end_seconds >= min_break_seconds:
            intervals.append((left.end_seconds, right.start_seconds))
    if duration_seconds - film_runs[-1].end_seconds >= 20.0:
        intervals.append((film_runs[-1].end_seconds, duration_seconds))
    return intervals


def _refine_boundary(
    center_seconds: float,
    *,
    target_present: bool,
    duration_seconds: float,
    score_at_times,
    deadline: float,
) -> tuple[float, dict]:
    if deadline - time.perf_counter() < 3.0:
        return center_seconds, {"status": "SKIPPED_TIME_BUDGET", "coarse_seconds": center_seconds}
    start = max(0.0, center_seconds - LOCAL_RADIUS_SECONDS)
    end = min(duration_seconds, center_seconds + LOCAL_RADIUS_SECONDS)
    times = []
    current = start
    while current <= end + 1e-6:
        times.append(round(current, 6))
        current += LOCAL_STEP_SECONDS
    scores = score_at_times(times)
    states = [(seconds, scores[seconds] >= DEFAULT_PRESENT_THRESHOLD) for seconds in times if seconds in scores]
    candidates = []
    for index in range(1, max(1, len(states) - LOCAL_PERSISTENCE + 1)):
        before_state = states[index - 1][1]
        persistent = states[index:index + LOCAL_PERSISTENCE]
        if before_state != target_present and len(persistent) == LOCAL_PERSISTENCE and all(
            state == target_present for _seconds, state in persistent
        ):
            candidates.append(persistent[0][0])
    selected = min(candidates, key=lambda value: abs(value - center_seconds)) if candidates else center_seconds
    return selected, {
        "status": "REFINED" if candidates else "NO_PERSISTENT_TRANSITION",
        "coarse_seconds": center_seconds,
        "selected_seconds": selected,
        "target_present": target_present,
        "observations": len(states),
    }


def _write_outputs(
    *,
    film_root: Path,
    metadata: VideoMetadata,
    channel: str,
    config_path: Path,
    intervals_seconds: list[tuple[float, float]],
    details: dict,
    runtime_seconds: float,
) -> dict:
    final_root = film_root / "final"
    final_root.mkdir(parents=True, exist_ok=True)
    intervals_frames = []
    for start, end in intervals_seconds:
        left = 1 if start <= 0 else frame_for_seconds(start, fps=metadata.fps, total_frames=metadata.total_frames)
        right = metadata.total_frames if end >= metadata.duration_seconds else frame_for_seconds(
            end, fps=metadata.fps, total_frames=metadata.total_frames
        )
        if right > left:
            intervals_frames.append((left, right))
    rate100 = int(round(metadata.fps * 100))
    txt = (
        f"FILE PROCESSING COMPLETE {metadata.total_frames} FRAMES AT {rate100:5d}\n"
        "-------------------\n"
        + "".join(f"{left}\t{right}\n" for left, right in intervals_frames)
    )
    edl = "".join(
        f"{max(left - 1, 0) / metadata.fps:.2f}\t{max(right - 1, 0) / metadata.fps:.2f}\t0\n"
        for left, right in intervals_frames
    )
    log = (
        "=" * 72
        + "\nMAKROMODUS AKTIV\n"
        + f"Sender: {channel}\n"
        + f"Grobe Werbeblöcke: {len(intervals_frames)}\n"
        + f"Laufzeit: {runtime_seconds:.3f} s\n"
        + "Vollanalyse bei Bedarf: comskip-final.exe --full-analysis <Video>\n"
        + "=" * 72
        + "\n"
    )
    marker = (
        "MAKROMODUS AKTIV\n"
        f"Sender: {channel}\n"
        "Verarbeitung: dynamisches Logo, grobe Filmblöcke, lokale Kantenprüfung\n"
        f"Erkannte Ausschlussblöcke: {len(intervals_frames)}\n"
        "Korrektur in ComskipGUI: zum Block springen, richtige Kante suchen und B oder E drücken.\n"
        "Vollanalyse: comskip-final.exe --full-analysis <Video>\n"
    )
    (final_root / "final.txt").write_text(txt, encoding="ascii", newline="\n")
    (final_root / "final.edl").write_text(edl, encoding="ascii", newline="\n")
    (final_root / "final.log").write_text(log, encoding="utf-8", newline="\n")
    (film_root / MARKER_NAME).write_text(marker, encoding="utf-8", newline="\n")
    result = {
        "schema_version": "commercial-logo-macro-v1",
        "processing_mode": PROCESSING_MODE,
        "macro_mode": True,
        "detected_channel": channel,
        "channel_list": str(config_path),
        "video_metadata": asdict(metadata),
        "estimated_intervals_seconds": [list(interval) for interval in intervals_seconds],
        "final_stage_intervals": [list(interval) for interval in intervals_frames],
        "analysis": details,
        "runtime_seconds": {"total": runtime_seconds},
        "outputs": {
            "final_stage_txt": str(final_root / "final.txt"),
            "macro_mode_marker": str(film_root / MARKER_NAME),
        },
    }
    (film_root / "diagnostic.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_commercial_macro_mode(
    *,
    video: Path,
    film_root: Path,
    ffprobe: Path,
    channel: str,
    config_path: Path,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    sample_seconds: float = DEFAULT_SAMPLE_SECONDS,
) -> dict:
    started = time.perf_counter()
    deadline = started + time_budget_seconds
    metadata = probe_video(ffprobe, video)
    capture = None
    try:
        capture, score_at_times, typical_score, overlay_detail = learn_macro_overlay(video, metadata)
        if score_at_times is None:
            raise RuntimeError("Makromodus konnte für diese Aufnahme kein stabiles Logo lernen")
        scores: dict[float, float] = {}
        stage_details = []
        for stage_number, times in enumerate(
            progressive_sample_stages(metadata.duration_seconds, sample_seconds), 1
        ):
            if deadline - time.perf_counter() < 4.0:
                break
            stage_started = time.perf_counter()
            measured = score_at_times(times)
            scores.update(measured)
            stage_details.append(
                {
                    "stage": stage_number,
                    "requested": len(times),
                    "measured": len(measured),
                    "runtime_seconds": time.perf_counter() - stage_started,
                }
            )
        samples = [
            MacroSample(seconds, score, score >= DEFAULT_PRESENT_THRESHOLD)
            for seconds, score in sorted(scores.items())
        ]
        runs, film_runs = build_film_runs(samples, duration_seconds=metadata.duration_seconds)
        if not film_runs:
            raise RuntimeError("Makromodus fand keinen plausiblen langen Filmblock")
        coarse = intervals_from_film_runs(film_runs, duration_seconds=metadata.duration_seconds)
        refined = []
        refinements = []
        for start_seconds, end_seconds in coarse:
            start = start_seconds
            end = end_seconds
            if start_seconds > 0:
                start, detail = _refine_boundary(
                    start_seconds,
                    target_present=False,
                    duration_seconds=metadata.duration_seconds,
                    score_at_times=score_at_times,
                    deadline=deadline,
                )
                refinements.append(detail)
            if end_seconds < metadata.duration_seconds:
                end, detail = _refine_boundary(
                    end_seconds,
                    target_present=True,
                    duration_seconds=metadata.duration_seconds,
                    score_at_times=score_at_times,
                    deadline=deadline,
                )
                refinements.append(detail)
            if end > start:
                refined.append((start, end))
        runtime = time.perf_counter() - started
        details = {
            "strategy": "dynamic_logo_progressive_macro_grid_plus_local_transition_refinement",
            "time_budget_seconds": time_budget_seconds,
            "time_budget_exceeded": runtime > time_budget_seconds,
            "sample_seconds": sample_seconds,
            "present_threshold": DEFAULT_PRESENT_THRESHOLD,
            "dynamic_overlay": overlay_detail,
            "typical_distributed_score": typical_score,
            "sample_stages": stage_details,
            "samples_measured": len(samples),
            "state_runs": [asdict(run) for run in runs],
            "film_runs": [asdict(run) for run in film_runs],
            "coarse_intervals_seconds": [list(interval) for interval in coarse],
            "refinements": refinements,
        }
        return _write_outputs(
            film_root=film_root,
            metadata=metadata,
            channel=channel,
            config_path=config_path,
            intervals_seconds=refined,
            details=details,
            runtime_seconds=runtime,
        )
    finally:
        if capture is not None:
            capture.release()
