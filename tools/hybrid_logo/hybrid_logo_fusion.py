from __future__ import annotations

import argparse
import bisect
import csv
import json
import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = "hybrid-logo-v1"
PRESENT = "PRESENT"
ABSENT = "ABSENT"
CONFLICT = "CONFLICT"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RawLogoFinderPoint:
    frame: int
    time_seconds: float
    score: float
    sample_kind: str


@dataclass(frozen=True)
class ComskipObservation:
    frame: int
    time_seconds: float
    good_edge: float
    local_state: str
    local_state_start: bool
    local_state_end: bool
    global_logo_percentage: float
    global_logo_enabled: bool


@dataclass(frozen=True)
class CoarseStateChange:
    from_state: str
    to_state: str
    candidate_index: int
    confirmed_index: int


@dataclass(frozen=True)
class RefinedStateChange:
    from_state: str
    to_state: str
    frame: int
    time_seconds: float
    precision: str


@dataclass(frozen=True)
class StabilizationResult:
    coarse_points: tuple[RawLogoFinderPoint, ...]
    filtered_scores: tuple[float, ...]
    evidence_states: tuple[str, ...]
    state_changes: tuple[RefinedStateChange, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stabilize and PTS-align independent Comskip/LogoFinder observations."
    )
    parser.add_argument("--timeline", type=Path, required=True, help="Phase-1 hybrid_logo_timeline.jsonl")
    parser.add_argument("--metadata", type=Path, required=True, help="Phase-1 hybrid_logo_metadata.json")
    parser.add_argument("--comskip-raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="hybrid-logo-v1.jsonl output")
    parser.add_argument("--absent-threshold", type=float, default=0.38)
    parser.add_argument("--present-threshold", type=float, default=0.46)
    parser.add_argument("--boundary-threshold", type=float, default=0.42)
    parser.add_argument("--median-window", type=int, default=3)
    parser.add_argument("--persistence-samples", type=int, default=2)
    parser.add_argument("--frame-persistence", type=int, default=2)
    parser.add_argument("--max-alignment-seconds", type=float, default=0.10)
    return parser.parse_args()


def load_logofinder_points(path: Path) -> list[RawLogoFinderPoint]:
    points: list[RawLogoFinderPoint] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                row = json.loads(line)
                points.append(
                    RawLogoFinderPoint(
                        frame=int(row["frame"]),
                        time_seconds=float(row["time_seconds"]),
                        score=float(row["logofinder_score"]),
                        sample_kind=str(row["sample_kind"]),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid LogoFinder timeline line {line_number}: {exc}") from exc
    if not points:
        raise ValueError("LogoFinder timeline is empty")
    return sorted(points, key=lambda point: (point.time_seconds, point.frame))


def load_comskip_points(path: Path) -> list[ComskipObservation]:
    points: list[ComskipObservation] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            points.append(
                ComskipObservation(
                    frame=int(row["frame"]),
                    time_seconds=float(row["time_seconds"]),
                    good_edge=float(row["comskip_good_edge"]),
                    local_state=PRESENT if bool(int(row["comskip_present"])) else ABSENT,
                    local_state_start=bool(int(row["local_state_start"])),
                    local_state_end=bool(int(row["local_state_end"])),
                    global_logo_percentage=float(row["global_logo_percentage"]),
                    global_logo_enabled=bool(int(row["global_logo_enabled"])),
                )
            )
    if not points:
        raise ValueError("Comskip raw timeline is empty")
    return sorted(points, key=lambda point: (point.time_seconds, point.frame))


def validate_parameters(args: argparse.Namespace) -> None:
    if not 0 <= args.absent_threshold < args.present_threshold <= 1:
        raise ValueError("Thresholds must satisfy 0 <= absent < present <= 1")
    if not args.absent_threshold <= args.boundary_threshold <= args.present_threshold:
        raise ValueError("--boundary-threshold must lie inside the hysteresis band")
    if args.median_window < 1 or args.median_window % 2 == 0:
        raise ValueError("--median-window must be a positive odd number")
    if args.persistence_samples < 1:
        raise ValueError("--persistence-samples must be positive")
    if args.frame_persistence < 1:
        raise ValueError("--frame-persistence must be positive")
    if args.max_alignment_seconds < 0:
        raise ValueError("--max-alignment-seconds must not be negative")


def effective_stabilization_samples(
    metadata: dict, median_window: int, persistence_samples: int
) -> tuple[int, int, str]:
    """Preserve Phase-2A's temporal filter widths on a dense frame timeline."""
    timeline = metadata.get("timeline", {})
    if timeline.get("mode") != "every_decodable_frame":
        return median_window, persistence_samples, "timeline_samples"

    step_seconds = float(timeline["coarse_step_seconds"])
    if step_seconds <= 0:
        raise ValueError("Dense timeline step must be positive")
    samples_per_second = 1.0 / step_seconds
    effective_median = max(1, int(round(median_window * samples_per_second)))
    if effective_median % 2 == 0:
        effective_median += 1
    effective_persistence = max(1, int(round(persistence_samples * samples_per_second)))
    return effective_median, effective_persistence, "phase2a_seconds_preserved"


def classify_score(score: float, absent_threshold: float, present_threshold: float) -> str:
    if score <= absent_threshold:
        return ABSENT
    if score >= present_threshold:
        return PRESENT
    return UNKNOWN


def centered_median(points: list[RawLogoFinderPoint], window: int) -> list[float]:
    radius = window // 2
    return [
        float(statistics.median(point.score for point in points[max(0, index - radius) : index + radius + 1]))
        for index in range(len(points))
    ]


def confirmed_changes(evidence: list[str], persistence_samples: int) -> list[CoarseStateChange]:
    current = UNKNOWN
    pending = UNKNOWN
    pending_start = 0
    pending_count = 0
    changes: list[CoarseStateChange] = []
    for index, observed in enumerate(evidence):
        if observed == UNKNOWN:
            pending = UNKNOWN
            pending_count = 0
            continue
        if observed == current:
            pending = UNKNOWN
            pending_count = 0
            continue
        if observed != pending:
            pending = observed
            pending_start = index
            pending_count = 1
        else:
            pending_count += 1
        if pending_count >= persistence_samples:
            changes.append(
                CoarseStateChange(
                    from_state=current,
                    to_state=observed,
                    candidate_index=pending_start,
                    confirmed_index=index,
                )
            )
            current = observed
            pending = UNKNOWN
            pending_count = 0
    return changes


def find_persistent_target(
    points_by_frame: dict[int, RawLogoFinderPoint],
    *,
    start_frame: int,
    end_frame: int,
    target_state: str,
    boundary_threshold: float,
    frame_persistence: int,
) -> RawLogoFinderPoint | None:
    candidates = [
        points_by_frame[frame]
        for frame in range(start_frame, end_frame + 1)
        if frame in points_by_frame
    ]
    run: list[RawLogoFinderPoint] = []
    for point in candidates:
        supports_target = point.score >= boundary_threshold if target_state == PRESENT else point.score < boundary_threshold
        if not supports_target:
            run = []
            continue
        if run and point.frame != run[-1].frame + 1:
            run = []
        run.append(point)
        if len(run) >= frame_persistence:
            return run[0]
    return None


def refine_changes(
    all_points: list[RawLogoFinderPoint],
    coarse: list[RawLogoFinderPoint],
    evidence: list[str],
    changes: list[CoarseStateChange],
    *,
    absent_threshold: float,
    present_threshold: float,
    boundary_threshold: float,
    frame_persistence: int,
) -> list[RefinedStateChange]:
    refined: list[RefinedStateChange] = []
    points_by_frame = {point.frame: point for point in all_points}
    for change in changes:
        candidate = coarse[change.candidate_index]
        if change.from_state == UNKNOWN:
            refined.append(
                RefinedStateChange(
                    from_state=UNKNOWN,
                    to_state=change.to_state,
                    frame=candidate.frame,
                    time_seconds=candidate.time_seconds,
                    precision="coarse_initial_state",
                )
            )
            continue
        previous_index = change.candidate_index - 1
        while previous_index > 0 and evidence[previous_index] != change.from_state:
            previous_index -= 1
        start = coarse[max(0, previous_index)]
        end = coarse[change.confirmed_index]
        exact = find_persistent_target(
            points_by_frame,
            start_frame=start.frame,
            end_frame=end.frame,
            target_state=change.to_state,
            boundary_threshold=boundary_threshold,
            frame_persistence=frame_persistence,
        )
        point = exact or candidate
        refined.append(
            RefinedStateChange(
                from_state=change.from_state,
                to_state=change.to_state,
                frame=point.frame,
                time_seconds=point.time_seconds,
                precision="frame_persistent" if exact else "coarse_fallback",
            )
        )
    return refined


def stabilize(
    all_points: list[RawLogoFinderPoint],
    *,
    absent_threshold: float,
    present_threshold: float,
    boundary_threshold: float,
    median_window: int,
    persistence_samples: int,
    frame_persistence: int,
) -> StabilizationResult:
    coarse = [point for point in all_points if point.sample_kind in ("coarse", "frame")]
    if not coarse:
        raise ValueError("Timeline contains no coarse points")
    filtered = centered_median(coarse, median_window)
    evidence = [classify_score(score, absent_threshold, present_threshold) for score in filtered]
    changes = confirmed_changes(evidence, persistence_samples)
    refined = refine_changes(
        all_points,
        coarse,
        evidence,
        changes,
        absent_threshold=absent_threshold,
        present_threshold=present_threshold,
        boundary_threshold=boundary_threshold,
        frame_persistence=frame_persistence,
    )
    return StabilizationResult(tuple(coarse), tuple(filtered), tuple(evidence), tuple(refined))


def stable_state_at(frame: int, changes: tuple[RefinedStateChange, ...]) -> str:
    state = UNKNOWN
    for change in changes:
        if frame < change.frame:
            break
        state = change.to_state
    return state


def stable_states_for_points(
    points: list[RawLogoFinderPoint], changes: tuple[RefinedStateChange, ...]
) -> list[str]:
    states: list[str] = []
    state = UNKNOWN
    change_index = 0
    for point in points:
        while change_index < len(changes) and changes[change_index].frame <= point.frame:
            state = changes[change_index].to_state
            change_index += 1
        states.append(state)
    return states


def nearest_filtered_score(frame: int, result: StabilizationResult) -> float:
    frames = [point.frame for point in result.coarse_points]
    index = bisect.bisect_left(frames, frame)
    candidates = [candidate for candidate in (index - 1, index) if 0 <= candidate < len(frames)]
    nearest = min(candidates, key=lambda candidate: abs(frames[candidate] - frame))
    return result.filtered_scores[nearest]


def nearest_filtered_scores(
    points: list[RawLogoFinderPoint], result: StabilizationResult
) -> list[float]:
    frames = [point.frame for point in result.coarse_points]
    values: list[float] = []
    for point in points:
        index = bisect.bisect_left(frames, point.frame)
        candidates = [candidate for candidate in (index - 1, index) if 0 <= candidate < len(frames)]
        nearest = min(candidates, key=lambda candidate: abs(frames[candidate] - point.frame))
        values.append(result.filtered_scores[nearest])
    return values


def local_confidence(score: float, state: str, absent_threshold: float, present_threshold: float) -> float:
    if state == PRESENT and score >= present_threshold:
        return min(1.0, (score - present_threshold) / max(1e-9, 1.0 - present_threshold))
    if state == ABSENT and score <= absent_threshold:
        return min(1.0, (absent_threshold - score) / max(1e-9, absent_threshold))
    return 0.0


class ComskipAligner:
    def __init__(self, points: list[ComskipObservation], max_delta_seconds: float):
        self.points = points
        self.times = [point.time_seconds for point in points]
        self.max_delta_seconds = max_delta_seconds

    def nearest(self, time_seconds: float) -> tuple[ComskipObservation | None, float | None]:
        index = bisect.bisect_left(self.times, time_seconds)
        candidates = [candidate for candidate in (index - 1, index) if 0 <= candidate < len(self.points)]
        if not candidates:
            return None, None
        best_index = min(candidates, key=lambda candidate: abs(self.times[candidate] - time_seconds))
        delta = self.times[best_index] - time_seconds
        if abs(delta) > self.max_delta_seconds:
            return None, delta
        return self.points[best_index], delta


def fusion_state(logofinder_state: str, usable: bool, comskip: ComskipObservation | None) -> tuple[str, str]:
    if comskip is None:
        return UNKNOWN, "missing_comskip_pts_alignment"
    if logofinder_state == UNKNOWN or not usable:
        return comskip.local_state, "comskip_local_used_while_logofinder_unknown"
    if logofinder_state == comskip.local_state:
        if logofinder_state == PRESENT:
            return PRESENT, "sensors_agree_present"
        return ABSENT, "sensors_agree_absent"
    return CONFLICT, "sensors_disagree"


def global_reliabilities(comskip: list[ComskipObservation]) -> tuple[str, str]:
    comskip_level = (
        "ACCEPTED_BY_EXISTING_GATE" if comskip[0].global_logo_enabled else "REJECTED_BY_EXISTING_GATE"
    )
    return comskip_level, "UNASSESSED_PHASE_2A"


def observation_record(
    point: RawLogoFinderPoint,
    *,
    stabilization: StabilizationResult,
    aligner: ComskipAligner,
    absent_threshold: float,
    present_threshold: float,
    comskip_global_reliability: str,
    logofinder_global_reliability: str,
    stabilized_state: str | None = None,
    filtered_score: float | None = None,
) -> dict:
    state = stabilized_state if stabilized_state is not None else stable_state_at(point.frame, stabilization.state_changes)
    raw_evidence = classify_score(point.score, absent_threshold, present_threshold)
    usable = state in (PRESENT, ABSENT)
    confidence = local_confidence(point.score, state, absent_threshold, present_threshold)
    comskip, delta = aligner.nearest(point.time_seconds)
    fused, reason = fusion_state(state, usable, comskip)
    if fused in (PRESENT, ABSENT, CONFLICT) and raw_evidence == UNKNOWN:
        reason += "_hysteresis_hold"
    elif fused in (PRESENT, ABSENT, CONFLICT) and raw_evidence not in (state, UNKNOWN):
        reason += "_persistence_rejected_opposite_sample"
    return {
        "record_type": "observation",
        "schema_version": SCHEMA_VERSION,
        "time_seconds": round(point.time_seconds, 6),
        "logofinder_pts_seconds": round(point.time_seconds, 6),
        "logofinder_frame": point.frame,
        "logofinder_sample_kind": point.sample_kind,
        "comskip_pts_seconds": round(comskip.time_seconds, 6) if comskip else None,
        "comskip_frame": comskip.frame if comskip else None,
        "pts_alignment_delta_seconds": round(delta, 9) if delta is not None else None,
        "comskip_local_state": comskip.local_state if comskip else UNKNOWN,
        "comskip_local_confidence": round(comskip.good_edge, 9) if comskip else None,
        "comskip_local_confidence_kind": "currentGoodEdge_raw" if comskip else None,
        "comskip_local_state_start": comskip.local_state_start if comskip else None,
        "comskip_local_state_end": comskip.local_state_end if comskip else None,
        "comskip_global_reliability": comskip_global_reliability,
        "comskip_global_logo_percentage": round(comskip.global_logo_percentage, 9) if comskip else None,
        "logofinder_raw_score": round(point.score, 9),
        "logofinder_filtered_score": round(
            filtered_score if filtered_score is not None else nearest_filtered_score(point.frame, stabilization), 9
        ),
        "logofinder_raw_evidence": raw_evidence,
        "logofinder_stabilized_state": state,
        "logofinder_measurement_usable": usable,
        "logofinder_local_confidence": round(confidence, 9),
        "logofinder_global_reliability": logofinder_global_reliability,
        "fusion_state": fused,
        "fusion_reason": reason,
    }


def state_counts(records: Iterable[dict]) -> dict[str, int]:
    counts = {PRESENT: 0, ABSENT: 0, CONFLICT: 0, UNKNOWN: 0}
    for record in records:
        counts[record["fusion_state"]] += 1
    return counts


def conflict_ranges(records: list[dict], coarse_step_seconds: float) -> list[dict]:
    ranges: list[dict] = []
    active: list[dict] = []
    for record in records:
        if record["fusion_state"] == CONFLICT and (
            not active or record["time_seconds"] - active[-1]["time_seconds"] <= coarse_step_seconds * 1.5
        ):
            active.append(record)
            continue
        if active:
            ranges.append(_conflict_range(active, coarse_step_seconds))
            active = []
        if record["fusion_state"] == CONFLICT:
            active = [record]
    if active:
        ranges.append(_conflict_range(active, coarse_step_seconds))
    return sorted(ranges, key=lambda item: item["duration_seconds"], reverse=True)


def _conflict_range(records: list[dict], coarse_step_seconds: float) -> dict:
    return {
        "start_seconds": records[0]["time_seconds"],
        "end_seconds": records[-1]["time_seconds"],
        "duration_seconds": round(records[-1]["time_seconds"] - records[0]["time_seconds"] + coarse_step_seconds, 6),
        "start_logofinder_frame": records[0]["logofinder_frame"],
        "end_logofinder_frame": records[-1]["logofinder_frame"],
        "sample_count": len(records),
    }


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def run(args: argparse.Namespace) -> dict:
    validate_parameters(args)
    tracemalloc.start()
    total_started = time.perf_counter()
    load_started = time.perf_counter()
    phase1_metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    logo_points = load_logofinder_points(args.timeline)
    comskip_points = load_comskip_points(args.comskip_raw)
    load_seconds = time.perf_counter() - load_started

    effective_median_window, effective_persistence_samples, stabilization_units = (
        effective_stabilization_samples(
            phase1_metadata, args.median_window, args.persistence_samples
        )
    )

    stabilize_started = time.perf_counter()
    stabilization = stabilize(
        logo_points,
        absent_threshold=args.absent_threshold,
        present_threshold=args.present_threshold,
        boundary_threshold=args.boundary_threshold,
        median_window=effective_median_window,
        persistence_samples=effective_persistence_samples,
        frame_persistence=args.frame_persistence,
    )
    stabilize_seconds = time.perf_counter() - stabilize_started

    aligner = ComskipAligner(comskip_points, args.max_alignment_seconds)
    comskip_reliability, logofinder_reliability = global_reliabilities(comskip_points)
    stabilized_states = stable_states_for_points(logo_points, stabilization.state_changes)
    filtered_scores = nearest_filtered_scores(logo_points, stabilization)
    records = [
        observation_record(
            point,
            stabilization=stabilization,
            aligner=aligner,
            absent_threshold=args.absent_threshold,
            present_threshold=args.present_threshold,
            comskip_global_reliability=comskip_reliability,
            logofinder_global_reliability=logofinder_reliability,
            stabilized_state=stabilized_state,
            filtered_score=filtered_score,
        )
        for point, stabilized_state, filtered_score in zip(
            logo_points, stabilized_states, filtered_scores
        )
    ]
    coarse_records = [
        record
        for record in records
        if record["logofinder_sample_kind"] in ("coarse", "frame")
    ]
    coarse_step = float(phase1_metadata["timeline"]["coarse_step_seconds"])
    peak_memory = tracemalloc.get_traced_memory()[1]

    metadata_record = {
        "record_type": "metadata",
        "schema_version": SCHEMA_VERSION,
        "primary_axis": "time_seconds",
        "video": phase1_metadata["video"],
        "video_metadata": phase1_metadata["video_metadata"],
        "alignment": {
            "method": "nearest_comskip_pts",
            "max_delta_seconds": args.max_alignment_seconds,
            "logofinder_time_conversion": "container_frame / container_fps",
            "comskip_time_source": "exported frame PTS",
        },
        "stabilization": {
            "absent_threshold": args.absent_threshold,
            "present_threshold": args.present_threshold,
            "boundary_threshold": args.boundary_threshold,
            "uncertainty_band": [args.absent_threshold, args.present_threshold],
            "requested_centered_median_window": args.median_window,
            "requested_persistence": args.persistence_samples,
            "effective_centered_median_window_samples": effective_median_window,
            "effective_persistence_samples": effective_persistence_samples,
            "parameter_units": stabilization_units,
            "frame_persistence_samples": args.frame_persistence,
            "coarse_step_seconds": coarse_step,
        },
        "global_reliability": {
            "comskip": comskip_reliability,
            "comskip_logo_percentage": comskip_points[0].global_logo_percentage,
            "logofinder": logofinder_reliability,
            "logofinder_heatmap_confidence": phase1_metadata["logofinder"]["overlay"]["confidence"],
            "note": "Global reliability annotates but never deletes local observations.",
        },
        "state_change_count": len(stabilization.state_changes),
    }

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    write_started = time.perf_counter()
    write_jsonl(output, [metadata_record, *records])
    write_seconds = time.perf_counter() - write_started
    total_seconds = time.perf_counter() - total_started
    summary = {
        "schema_version": SCHEMA_VERSION,
        "sidecar": str(output),
        "sidecar_bytes": output.stat().st_size,
        "observation_count": len(records),
        "coarse_observation_count": len(coarse_records),
        "coarse_fusion_counts": state_counts(coarse_records),
        "max_conflict_ranges": conflict_ranges(coarse_records, coarse_step)[:20],
        "state_changes": [change.__dict__ for change in stabilization.state_changes],
        "performance_seconds": {
            "input_loading": load_seconds,
            "stabilization": stabilize_seconds,
            "sidecar_write": write_seconds,
            "total": total_seconds,
        },
        "peak_traced_memory_bytes": peak_memory,
    }
    summary_path = output.with_name(output.stem + "-summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tracemalloc.stop()
    return summary


def main() -> int:
    try:
        summary = run(parse_args())
    except Exception as exc:
        print(f"hybrid-logo-fusion: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
