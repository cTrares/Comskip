from __future__ import annotations

import argparse
import json
import shutil
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
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
DEFAULT_MIN_FILM_RUN_SECONDS = 7.0 * 60.0
DEFAULT_MIN_BREAK_SECONDS = 150.0
DEFAULT_BRIDGE_SECONDS = 90.0
PROTECTED_PRESENT_SECONDS = 90.0
LOCAL_STEP_SECONDS = 2.0
LOCAL_RADIUS_SECONDS = 80.0
LOCAL_PERSISTENCE = 3
LOCAL_MEDIAN_RADIUS = 2
RETURN_SAFETY_CORRIDOR_SECONDS = 180.0
RETURN_RELAPSE_SECONDS = 24.0
RETURN_PROMO_ISLAND_RELAPSE_SECONDS = 6.0
RETURN_PROMO_ISLAND_MINIMUM_SECONDS = 50.0
RETURN_CONFIRMATION_SECONDS = 40.0
RETURN_MIN_PRESENT_FRACTION = 0.72
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


def _reference_from_known_rect(video: Path, metadata: VideoMetadata, rect: tuple[int, int, int, int]):
    """Build the fast Python scorer after Comskip supplied only the logo rectangle."""
    from hybrid_logo_analysis import learning_sample_seconds, load_internal_logo_api

    api = load_internal_logo_api()
    (
        cv2,
        np,
        ProgramOverlay,
        OverlayReference,
        _detect_logo_by_heatmap,
        read_frame_at,
        crop_rect,
        normalize_gray,
        edge_image,
        build_template_mask,
        overlay_present_score,
        _overlay_present_score_from_crop,
    ) = api
    guard = min(LEARNING_EDGE_GUARD_SECONDS, metadata.duration_seconds * 0.12)
    sample_times = learning_sample_seconds(guard, metadata.duration_seconds - guard, 32)
    # Comskip stores inclusive maximum coordinates; the Python crop uses an
    # exclusive right/bottom edge.
    left, top, right, bottom = rect
    overlay = ProgramOverlay(
        rect=(left, top, right + 1, bottom + 1),
        source="comskip-recurring-mask-rect",
        confidence=1.0,
        sample_count=len(sample_times),
    )
    learning_capture = cv2.VideoCapture(str(video))
    crops = []
    try:
        for seconds in sample_times:
            frame = read_frame_at(learning_capture, seconds)
            if frame is None:
                continue
            crop = crop_rect(frame, overlay.rect)
            if crop.size:
                crops.append(normalize_gray(crop).astype(np.float32))
    finally:
        learning_capture.release()
    if len(crops) < 8:
        return None, None, None, {"status": "COMSKIP_RECT_REFERENCE_UNAVAILABLE"}
    reference_gray = np.median(np.stack(crops), axis=0).astype(np.uint8)
    reference_edges = edge_image(reference_gray)
    template_mask = build_template_mask(reference_gray)
    edge_mask = cv2.bitwise_and(
        cv2.dilate(reference_edges, np.ones((3, 3), np.uint8), iterations=1),
        template_mask,
    )
    if int(np.count_nonzero(edge_mask)) < 12:
        edge_mask = template_mask
    reference = OverlayReference(
        overlay=overlay,
        gray=reference_gray,
        edges=reference_edges,
        edge_mask=edge_mask,
        template_mask=template_mask,
    )
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

    typical_times = learning_sample_seconds(guard, metadata.duration_seconds - guard, 11)
    typical_values = list(score_at_times(typical_times).values())
    typical_score = statistics.median(typical_values) if typical_values else None
    return capture, score_at_times, typical_score, {
        "status": "COMSKIP_RECT_REFERENCE_LEARNED",
        "source": overlay.source,
        "rect_discovered_for_this_recording": list(overlay.rect),
        "reference_frames": len(crops),
        "typical_distributed_score": typical_score,
    }


def learn_macro_overlay_via_comskip(
    *,
    video: Path,
    metadata: VideoMetadata,
    film_root: Path,
    ffmpeg: Path,
    comskip: Path,
    ini: Path,
):
    """Use only Comskip's fast multiwindow logo learner, never its full scan."""
    from multiwindow_logo_experiment import (
        SELECTED_MASK_NAME,
        candidate_quality,
        comskip_command,
        learning_window_artifacts,
        learning_windows,
        parse_mask,
        run_command,
        select_recurring_candidate,
    )

    args = argparse.Namespace(comskip=comskip, ini=ini)
    windows = learning_windows(metadata.duration_seconds)
    learning_root = film_root / "macro-comskip-logo"

    def process_window(window):
        artifacts = learning_window_artifacts(learning_root, window.index)
        artifacts.root.mkdir(parents=True, exist_ok=True)
        extract_command = [
            str(ffmpeg), "-hide_banner", "-loglevel", "warning", "-y",
            "-ss", f"{window.start_seconds:.6f}", "-i", str(video),
            "-t", f"{window.end_seconds - window.start_seconds:.6f}",
            "-map", "0:v:0", "-an", "-sn", "-c:v", "copy",
            "-avoid_negative_ts", "make_zero", str(artifacts.clip),
        ]
        run_command(extract_command, log_path=artifacts.root / "ffmpeg.log")
        run_command(
            comskip_command(args, artifacts.clip, artifacts.root, artifacts.output_name, raw=True),
            log_path=artifacts.root / "cmd.log",
            accepted_exit_codes=(0, 1),
        )
        if not artifacts.mask.is_file() or not artifacts.raw.is_file():
            return None
        return parse_mask(artifacts.mask, window, candidate_quality(artifacts.raw))

    with ThreadPoolExecutor(max_workers=len(windows), thread_name_prefix="macro-logo-learn") as executor:
        candidates = [candidate for candidate in executor.map(process_window, windows) if candidate is not None]
    selected, comparisons = select_recurring_candidate(candidates)
    if selected is None:
        return None, None, None, {
            "status": "NO_RECURRING_COMSKIP_MASK",
            "candidate_count": len(candidates),
            "comparisons": comparisons,
        }
    selected_path = film_root / SELECTED_MASK_NAME
    shutil.copy2(selected.path, selected_path)
    capture, score_at_times, typical_score, detail = _reference_from_known_rect(
        video, metadata, selected.bbox
    )
    detail.update(
        {
            "fallback": "comskip-five-window-logo-learning",
            "selected_mask": str(selected_path),
            "support_count": selected.support_count,
            "candidate_count": len(candidates),
        }
    )
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
    """Return measured runs and film anchors after repairing short sensor holes.

    The ordering is intentional: short negative holes are joined to an already
    plausible program context before the minimum film duration is applied.
    This prevents a 20-60 second logo miss from discarding the final minutes of
    an otherwise long movie segment.
    """
    runs = _raw_runs(_median_states(sorted(samples, key=lambda item: item.seconds)), duration_seconds)
    repaired, _bridges = repair_state_runs(
        runs,
        min_film_context_seconds=min_film_run_seconds,
        bridge_seconds=bridge_seconds,
    )
    anchors = [run for run in repaired if run.present and run.duration_seconds >= min_film_run_seconds]
    if not anchors:
        present_runs = [run for run in repaired if run.present]
        if present_runs:
            longest = max(present_runs, key=lambda item: item.duration_seconds)
            if longest.duration_seconds >= min_film_run_seconds / 2.0:
                anchors = [longest]
    return runs, anchors


def _combined_present_run(left: MacroRun, right: MacroRun, gap: MacroRun) -> MacroRun:
    sample_count = left.sample_count + right.sample_count
    weighted_score = (
        left.median_score * left.sample_count + right.median_score * right.sample_count
    ) / max(1, sample_count)
    return MacroRun(
        start_seconds=left.start_seconds,
        end_seconds=right.end_seconds,
        present=True,
        sample_count=sample_count + gap.sample_count,
        median_score=weighted_score,
    )


def repair_state_runs(
    runs: list[MacroRun],
    *,
    min_film_context_seconds: float = DEFAULT_MIN_FILM_RUN_SECONDS,
    bridge_seconds: float = DEFAULT_BRIDGE_SECONDS,
) -> tuple[list[MacroRun], list[dict]]:
    """Bridge short negative holes only when one side is established program.

    Requiring an established context on at least one side stops a chain of
    short logo-positive station promos from growing into a synthetic movie.
    The operation is repeated because joining one tail can establish context
    for the next short sensor hole.
    """
    repaired = list(runs)
    bridges: list[dict] = []
    changed = True
    while changed:
        changed = False
        for index in range(1, len(repaired) - 1):
            left, gap, right = repaired[index - 1:index + 2]
            if not left.present or gap.present or not right.present:
                continue
            if gap.duration_seconds > bridge_seconds:
                continue
            if max(left.duration_seconds, right.duration_seconds) < min_film_context_seconds:
                continue
            combined = _combined_present_run(left, right, gap)
            bridges.append(
                {
                    "start_seconds": gap.start_seconds,
                    "end_seconds": gap.end_seconds,
                    "duration_seconds": gap.duration_seconds,
                    "left_context_seconds": left.duration_seconds,
                    "right_context_seconds": right.duration_seconds,
                    "combined_seconds": combined.duration_seconds,
                }
            )
            repaired[index - 1:index + 2] = [combined]
            changed = True
            break
    return repaired, bridges


def protected_present_runs(
    measured_runs: list[MacroRun],
    film_runs: list[MacroRun],
    *,
    minimum_seconds: float = PROTECTED_PRESENT_SECONDS,
) -> list[MacroRun]:
    """Return stable positive evidence not covered by a confirmed film run."""
    protected = []
    for run in measured_runs:
        if not run.present or run.duration_seconds < minimum_seconds:
            continue
        if any(
            film.start_seconds <= run.start_seconds and run.end_seconds <= film.end_seconds
            for film in film_runs
        ):
            continue
        protected.append(run)
    return protected


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


def guard_intervals_with_present_evidence(
    intervals: list[tuple[float, float]],
    positive_evidence: list[MacroRun],
    *,
    duration_seconds: float,
    min_internal_break_seconds: float = DEFAULT_MIN_BREAK_SECONDS,
) -> tuple[list[tuple[float, float]], list[dict]]:
    """Never let a proposed commercial silently cover stable positive evidence.

    The surrounding negative pieces remain usable if they are independently
    long enough.  Short leftovers become review points instead of cuts.
    """
    accepted: list[tuple[float, float]] = []
    reviews: list[dict] = []
    for interval_start, interval_end in intervals:
        pieces = [(interval_start, interval_end)]
        for evidence in positive_evidence:
            overlap_start = max(interval_start, evidence.start_seconds)
            overlap_end = min(interval_end, evidence.end_seconds)
            if overlap_end <= overlap_start:
                continue
            next_pieces = []
            for piece_start, piece_end in pieces:
                if evidence.end_seconds <= piece_start or evidence.start_seconds >= piece_end:
                    next_pieces.append((piece_start, piece_end))
                    continue
                if piece_start < evidence.start_seconds:
                    next_pieces.append((piece_start, evidence.start_seconds))
                if evidence.end_seconds < piece_end:
                    next_pieces.append((evidence.end_seconds, piece_end))
            pieces = next_pieces
            reviews.append(
                {
                    "seconds": (overlap_start + overlap_end) / 2.0,
                    "reason": "STABILER_POSITIVER_ABSCHNITT_IM_WERBEVORSCHLAG",
                    "range_seconds": [overlap_start, overlap_end],
                }
            )
        for piece_start, piece_end in pieces:
            edge_crop = piece_start <= 0.0 or piece_end >= duration_seconds
            required = 20.0 if edge_crop else min_internal_break_seconds
            if piece_end - piece_start >= required:
                accepted.append((piece_start, piece_end))
            elif piece_end > piece_start:
                reviews.append(
                    {
                        "seconds": (piece_start + piece_end) / 2.0,
                        "reason": "ZU_KURZER_UNSICHERER_RESTBLOCK",
                        "range_seconds": [piece_start, piece_end],
                    }
                )
    return accepted, reviews


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
    forward_radius = (
        RETURN_SAFETY_CORRIDOR_SECONDS if target_present else LOCAL_RADIUS_SECONDS
    )
    end = min(duration_seconds, center_seconds + forward_radius)
    times = []
    current = start
    while current <= end + 1e-6:
        times.append(round(current, 6))
        current += LOCAL_STEP_SECONDS
    scores = score_at_times(times)
    observations = [(seconds, scores[seconds]) for seconds in times if seconds in scores]
    states = []
    for index, (seconds, _score) in enumerate(observations):
        window = observations[
            max(0, index - LOCAL_MEDIAN_RADIUS):index + LOCAL_MEDIAN_RADIUS + 1
        ]
        stable_score = statistics.median(score for _time, score in window)
        states.append((seconds, stable_score >= DEFAULT_PRESENT_THRESHOLD))
    candidates = []
    for index in range(1, max(1, len(states) - LOCAL_PERSISTENCE + 1)):
        before_state = states[index - 1][1]
        persistent = states[index:index + LOCAL_PERSISTENCE]
        if before_state != target_present and len(persistent) == LOCAL_PERSISTENCE and all(
            state == target_present for _seconds, state in persistent
        ):
            candidates.append(persistent[0][0])
    selected = center_seconds
    sustained_candidates = []
    return_checks = []
    if candidates:
        nearest = min(candidates, key=lambda value: abs(value - center_seconds))
        selected = nearest
        if target_present:
            state_index = {seconds: index for index, (seconds, _state) in enumerate(states)}
            for candidate_number, candidate in enumerate(candidates):
                candidate_index = state_index[candidate]
                corridor_end = min(end, candidate + RETURN_SAFETY_CORRIDOR_SECONDS)
                tail = [
                    observation
                    for observation in states[candidate_index:]
                    if observation[0] <= corridor_end + 1e-6
                ]
                observed_seconds = (
                    tail[-1][0] - candidate + LOCAL_STEP_SECONDS if tail else 0.0
                )
                present_fraction = (
                    sum(state for _seconds, state in tail) / max(1, len(tail))
                )
                negative_runs = _state_spans(tail, present=False)
                relapses = [
                    [run_start, run_end]
                    for run_start, run_end in negative_runs
                    if run_end - run_start >= RETURN_RELAPSE_SECONDS
                ]
                confirmed = (
                    observed_seconds >= RETURN_CONFIRMATION_SECONDS
                    and not relapses
                    and present_fraction >= RETURN_MIN_PRESENT_FRACTION
                )
                next_candidate = (
                    candidates[candidate_number + 1]
                    if candidate_number + 1 < len(candidates)
                    else None
                )
                promo_island_relapses = [
                    [run_start, run_end]
                    for run_start, run_end in negative_runs
                    if run_end - run_start >= RETURN_PROMO_ISLAND_RELAPSE_SECONDS
                    and next_candidate is not None
                    and run_end <= next_candidate + LOCAL_STEP_SECONDS
                ]
                promo_island = (
                    next_candidate is not None
                    and next_candidate - candidate >= RETURN_PROMO_ISLAND_MINIMUM_SECONDS
                    and bool(promo_island_relapses)
                )
                if promo_island:
                    confirmed = False
                return_checks.append(
                    {
                        "candidate_seconds": candidate,
                        "observed_seconds": observed_seconds,
                        "present_fraction": present_fraction,
                        "negative_relapses": relapses,
                        "promo_island_relapses": promo_island_relapses,
                        "rejected_as_logo_positive_promo_island": promo_island,
                        "confirmed": confirmed,
                    }
                )
                if confirmed:
                    sustained_candidates.append(candidate)
            if sustained_candidates:
                # The first logo return is accepted only if no substantial
                # logo-negative relapse follows in the three-minute corridor.
                # Short sensor holes stay tolerated; a second advertising phase
                # rejects the premature return and moves the edge forward.
                selected = min(sustained_candidates)
    return selected, {
        "status": "REFINED" if candidates else "NO_PERSISTENT_TRANSITION",
        "coarse_seconds": center_seconds,
        "selected_seconds": selected,
        "target_present": target_present,
        "observations": len(states),
        "temporal_filter": f"median_{LOCAL_MEDIAN_RADIUS * 2 + 1}_samples",
        "sustained_candidates": sustained_candidates,
        "return_safety_corridor_seconds": (
            RETURN_SAFETY_CORRIDOR_SECONDS if target_present else 0.0
        ),
        "return_checks": return_checks,
    }


def _state_spans(
    states: list[tuple[float, bool]], *, present: bool
) -> list[tuple[float, float]]:
    """Compact equally spaced state observations into time spans."""
    spans: list[tuple[float, float]] = []
    run_start: float | None = None
    previous_seconds: float | None = None
    for seconds, state in states:
        if state == present:
            if run_start is None:
                run_start = seconds
        elif run_start is not None:
            spans.append((run_start, seconds))
            run_start = None
        previous_seconds = seconds
    if run_start is not None and previous_seconds is not None:
        spans.append((run_start, previous_seconds + LOCAL_STEP_SECONDS))
    return spans


def _write_outputs(
    *,
    film_root: Path,
    metadata: VideoMetadata,
    channel: str,
    config_path: Path,
    intervals_seconds: list[tuple[float, float]],
    review_markers: list[dict],
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
    marker_rows = []
    marker_details = []
    occupied = intervals_frames
    for review in review_markers:
        marker_frame = frame_for_seconds(
            float(review["seconds"]), fps=metadata.fps, total_frames=metadata.total_frames
        )
        if any(left <= marker_frame <= right for left, right in occupied):
            continue
        if any(existing == marker_frame for existing, _detail in marker_details):
            continue
        marker_rows.append((marker_frame, marker_frame))
        marker_details.append((marker_frame, review))
    rate100 = int(round(metadata.fps * 100))
    txt = (
        f"FILE PROCESSING COMPLETE {metadata.total_frames} FRAMES AT {rate100:5d}\n"
        "-------------------\n"
        + "".join(
            f"{left}\t{right}\n"
            for left, right in sorted([*intervals_frames, *marker_rows])
        )
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
        + f"Orange Prüfmarker: {len(marker_rows)}\n"
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
        f"Orange Prüfmarker: {len(marker_rows)}\n"
        "Prüfmarker sind Null-Längen-Blöcke: M/N springt dorthin, die EDL schneidet sie nicht.\n"
        "Korrektur in ComskipGUI: zum Block springen, richtige Kante suchen und B oder E drücken.\n"
        "Vollanalyse: comskip-final.exe --full-analysis <Video>\n"
    )
    (final_root / "final.txt").write_text(txt, encoding="ascii", newline="\n")
    (final_root / "final.edl").write_text(edl, encoding="ascii", newline="\n")
    (final_root / "final.log").write_text(log, encoding="utf-8", newline="\n")
    review_text = "".join(
        f"{frame}\t{float(detail['seconds']):.2f} s\t{detail['reason']}\t"
        f"{detail.get('range_seconds', [])}\n"
        for frame, detail in marker_details
    )
    (final_root / "final.review-markers.txt").write_text(
        review_text, encoding="utf-8", newline="\n"
    )
    (film_root / MARKER_NAME).write_text(marker, encoding="utf-8", newline="\n")
    result = {
        "schema_version": "commercial-logo-macro-v2",
        "processing_mode": PROCESSING_MODE,
        "macro_mode": True,
        "detected_channel": channel,
        "channel_list": str(config_path),
        "video_metadata": asdict(metadata),
        "estimated_intervals_seconds": [list(interval) for interval in intervals_seconds],
        "final_stage_intervals": [list(interval) for interval in intervals_frames],
        "review_markers": [
            {"frame": frame, **detail} for frame, detail in marker_details
        ],
        "analysis": details,
        "runtime_seconds": {"total": runtime_seconds},
        "outputs": {
            "final_stage_txt": str(final_root / "final.txt"),
            "review_markers": str(final_root / "final.review-markers.txt"),
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
    ffmpeg: Path,
    ffprobe: Path,
    comskip: Path,
    ini: Path,
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
        print("[Phase 2/6] LogoFinder: dynamisches Logo über die Aufnahme lernen", flush=True)
        capture, score_at_times, typical_score, overlay_detail = learn_macro_overlay(video, metadata)
        if score_at_times is None:
            print(
                "[Phase 2/6] Logo-Lernen: primärer Finder ohne Ergebnis; "
                "allgemeiner Mehrfenster-Lerner",
                flush=True,
            )
            capture, score_at_times, typical_score, fallback_detail = learn_macro_overlay_via_comskip(
                video=video,
                metadata=metadata,
                film_root=film_root,
                ffmpeg=ffmpeg,
                comskip=comskip,
                ini=ini,
            )
            overlay_detail = {"primary": overlay_detail, "selected": fallback_detail}
        if score_at_times is None:
            raise RuntimeError("Makromodus konnte mit beiden Lernwegen kein stabiles Logo lernen")
        scores: dict[float, float] = {}
        stage_details = []
        print("[Phase 3/6] Makroscanner: progressive Logo-Zeitachse aufbauen", flush=True)
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
        print("[Phase 4/6] Blockbildung: lange zusammenhängende Filmabschnitte bestimmen", flush=True)
        runs, film_runs = build_film_runs(samples, duration_seconds=metadata.duration_seconds)
        _repaired_runs, state_repairs = repair_state_runs(runs)
        if not film_runs:
            raise RuntimeError("Makromodus fand keinen plausiblen langen Filmblock")
        coarse = intervals_from_film_runs(film_runs, duration_seconds=metadata.duration_seconds)
        positive_evidence = protected_present_runs(runs, film_runs)
        guarded_coarse, review_markers = guard_intervals_with_present_evidence(
            coarse,
            positive_evidence,
            duration_seconds=metadata.duration_seconds,
        )
        refined = []
        refinements = []
        print("[Phase 5/6] Kantenprüfung: nur gefundene Übergänge lokal nachprüfen", flush=True)
        for start_seconds, end_seconds in guarded_coarse:
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
            "state_repairs": state_repairs,
            "film_runs": [asdict(run) for run in film_runs],
            "protected_present_runs": [asdict(run) for run in positive_evidence],
            "coarse_intervals_seconds": [list(interval) for interval in coarse],
            "guarded_coarse_intervals_seconds": [list(interval) for interval in guarded_coarse],
            "refinements": refinements,
        }
        print("[Phase 6/6] Ausgabe: TXT, EDL, Diagnose und Makromodus-Marker schreiben", flush=True)
        return _write_outputs(
            film_root=film_root,
            metadata=metadata,
            channel=channel,
            config_path=config_path,
            intervals_seconds=refined,
            review_markers=review_markers,
            details=details,
            runtime_seconds=runtime,
        )
    finally:
        if capture is not None:
            capture.release()
