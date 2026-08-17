from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class TimelinePoint:
    frame: int
    time_seconds: float
    score: float
    present: bool
    sample_kind: str


@dataclass(frozen=True)
class ComskipPoint:
    good_edge: float
    present: bool
    local_state_start: bool
    local_state_end: bool
    global_logo_percentage: float
    global_logo_enabled: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an experimental dense LogoFinder timeline and optionally align Comskip raw logo data."
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--comskip-raw", type=Path)
    parser.add_argument("--sample-seconds", type=float, default=1.0)
    parser.add_argument("--heatmap-samples", type=int, default=48)
    parser.add_argument("--reference-samples", type=int, default=24)
    parser.add_argument("--learning-start-seconds", type=float, default=0.0)
    parser.add_argument("--learning-end-seconds", type=float)
    parser.add_argument("--present-threshold", type=float, default=0.42)
    parser.add_argument("--sharp-delta", type=float, default=0.12)
    parser.add_argument("--refine-subdivisions", type=int, default=5)
    parser.add_argument(
        "--every-frame",
        action="store_true",
        help="Score the learned LogoFinder crop on every sequentially decodable frame.",
    )
    return parser.parse_args()


def load_internal_logo_api():
    from internal_logo_sensor import (
        OverlayReference,
        ProgramOverlay,
        build_template_mask,
        crop_rect,
        detect_logo_by_heatmap,
        edge_image,
        normalize_gray,
        overlay_present_score,
        read_frame_at,
    )
    import cv2
    import numpy as np
    return (
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
    )


def learning_sample_seconds(start: float, end: float, count: int) -> list[int]:
    """Return inclusive, evenly distributed whole-second samples inside one hard learning range."""
    first = int(start) if float(start).is_integer() else int(start) + 1
    last = int(end)
    if count <= 0 or last < first:
        return []
    if count == 1:
        return [int(round((first + last) / 2))]
    return sorted(
        {
            int(round(first + (last - first) * index / (count - 1)))
            for index in range(count)
        }
    )


def learn_overlay_in_range(
    *,
    video: Path,
    start_seconds: float,
    end_seconds: float,
    heatmap_samples: int,
    reference_samples: int,
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
):
    heatmap_started = time.perf_counter()
    heatmap_times = learning_sample_seconds(start_seconds, end_seconds, heatmap_samples)
    candidates = detect_logo_by_heatmap(
        video_path=video,
        sample_count=heatmap_samples,
        max_candidates=4,
        seconds_list=heatmap_times,
    )
    heatmap_seconds = time.perf_counter() - heatmap_started
    if not candidates:
        return None, None, heatmap_times, [], heatmap_seconds, 0.0
    best = candidates[0]
    overlay = ProgramOverlay(
        rect=best.rect,
        source=f"heatmap:{best.zone_name}",
        confidence=best.score,
        sample_count=best.frame_count,
    )

    reference_times = learning_sample_seconds(start_seconds, end_seconds, reference_samples)
    reference_started = time.perf_counter()
    capture = cv2.VideoCapture(str(video))
    crops = []
    try:
        if not capture.isOpened():
            return overlay, None, heatmap_times, reference_times, heatmap_seconds, time.perf_counter() - reference_started
        for seconds in reference_times:
            image = read_frame_at(capture, seconds)
            if image is None:
                continue
            crop = crop_rect(image, overlay.rect)
            if crop.size:
                crops.append(normalize_gray(crop).astype(np.float32))
    finally:
        capture.release()
    if len(crops) < max(4, reference_samples // 4):
        return overlay, None, heatmap_times, reference_times, heatmap_seconds, time.perf_counter() - reference_started
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
    return (
        overlay,
        reference,
        heatmap_times,
        reference_times,
        heatmap_seconds,
        time.perf_counter() - reference_started,
    )


class FrameScorer:
    def __init__(self, cv2, video: Path, reference, score_function: Callable):
        self._cv2 = cv2
        self._capture = cv2.VideoCapture(str(video))
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open video {video}")
        self._reference = reference
        self._score_function = score_function
        self._cache: dict[int, float] = {}
        self.request_count = 0
        self.seek_count = 0
        self.grab_count = 0

    def close(self) -> None:
        self._capture.release()

    def score(self, frame: int) -> float:
        frame = int(frame)
        cached = self._cache.get(frame)
        if cached is not None:
            return cached
        position = int(round(self._capture.get(self._cv2.CAP_PROP_POS_FRAMES)))
        forward_distance = frame - position
        if 0 <= forward_distance <= 250:
            while position < frame:
                if not self._capture.grab():
                    raise RuntimeError(f"Could not advance to frame {frame}")
                position += 1
                self.grab_count += 1
        else:
            self._capture.set(self._cv2.CAP_PROP_POS_FRAMES, frame)
            self.seek_count += 1
        ok, image = self._capture.read()
        if not ok or image is None:
            raise RuntimeError(f"Could not decode frame {frame}")
        value = float(self._score_function(self._reference, image))
        self._cache[frame] = value
        self.request_count += 1
        return value

    def score_every_frame(
        self, maximum_frames: int, *, fps: float, threshold: float
    ) -> list[TimelinePoint]:
        """Decode sequentially and apply only the already learned crop scorer."""
        points: list[TimelinePoint] = []
        self._capture.set(self._cv2.CAP_PROP_POS_FRAMES, 0)
        for frame in range(maximum_frames):
            ok, image = self._capture.read()
            if not ok or image is None:
                break
            value = float(self._score_function(self._reference, image))
            points.append(
                TimelinePoint(
                    frame=frame,
                    time_seconds=frame / fps,
                    score=value,
                    present=value >= threshold,
                    sample_kind="frame",
                )
            )
            self.request_count += 1
        return points


def frame_grid(total_frames: int, fps: float, sample_seconds: float) -> list[int]:
    if total_frames <= 0 or fps <= 0 or sample_seconds <= 0:
        return []
    step = max(1, int(round(fps * sample_seconds)))
    frames = list(range(0, total_frames, step))
    if frames[-1] != total_frames - 1:
        frames.append(total_frames - 1)
    return frames


def make_point(
    frame: int,
    fps: float,
    score_at: Callable[[int], float],
    threshold: float,
    sample_kind: str,
) -> TimelinePoint:
    score = score_at(frame)
    return TimelinePoint(
        frame=frame,
        time_seconds=frame / fps,
        score=score,
        present=score >= threshold,
        sample_kind=sample_kind,
    )


def refine_interval(
    start: TimelinePoint,
    end: TimelinePoint,
    *,
    fps: float,
    score_at: Callable[[int], float],
    threshold: float,
    sharp_delta: float,
    subdivisions: int,
) -> list[TimelinePoint]:
    """Refine one coarse interval, first by a small grid and then per frame near changes."""
    distance = end.frame - start.frame
    if distance <= 1:
        return []
    subdivisions = max(2, subdivisions)
    grid_frames = sorted(
        {start.frame, end.frame}
        | {start.frame + int(round(distance * index / subdivisions)) for index in range(1, subdivisions)}
    )
    grid = [make_point(frame, fps, score_at, threshold, "refine") for frame in grid_frames]
    pairs = list(zip(grid, grid[1:]))
    active_pairs = [(left, right) for left, right in pairs if left.present != right.present]
    if not active_pairs and abs(end.score - start.score) >= sharp_delta:
        active_pairs = [max(pairs, key=lambda pair: abs(pair[1].score - pair[0].score))]

    fine_frames: set[int] = set()
    for left, right in active_pairs:
        fine_frames.update(range(left.frame, right.frame + 1))
    fine = [make_point(frame, fps, score_at, threshold, "refine_frame") for frame in sorted(fine_frames)]
    by_frame = {point.frame: point for point in grid}
    by_frame.update({point.frame: point for point in fine})
    return list(by_frame.values())


def build_timeline(
    *,
    total_frames: int,
    fps: float,
    sample_seconds: float,
    score_at: Callable[[int], float],
    threshold: float,
    sharp_delta: float,
    subdivisions: int,
) -> list[TimelinePoint]:
    coarse = [
        make_point(frame, fps, score_at, threshold, "coarse")
        for frame in frame_grid(total_frames, fps, sample_seconds)
    ]
    by_frame = {point.frame: point for point in coarse}
    for left, right in zip(coarse, coarse[1:]):
        if left.present != right.present or abs(right.score - left.score) >= sharp_delta:
            for point in refine_interval(
                left,
                right,
                fps=fps,
                score_at=score_at,
                threshold=threshold,
                sharp_delta=sharp_delta,
                subdivisions=subdivisions,
            ):
                existing = by_frame.get(point.frame)
                if existing is None or existing.sample_kind != "coarse":
                    by_frame[point.frame] = point
    return [by_frame[frame] for frame in sorted(by_frame)]


def load_comskip_raw(path: Path | None) -> dict[int, ComskipPoint]:
    if path is None:
        return {}
    points: dict[int, ComskipPoint] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            frame = int(row["frame"])
            points[frame] = ComskipPoint(
                good_edge=float(row["comskip_good_edge"]),
                present=bool(int(row["comskip_present"])),
                local_state_start=bool(int(row["local_state_start"])),
                local_state_end=bool(int(row["local_state_end"])),
                global_logo_percentage=float(row["global_logo_percentage"]),
                global_logo_enabled=bool(int(row["global_logo_enabled"])),
            )
    return points


def agreement(logofinder_present: bool, comskip: ComskipPoint | None) -> str | None:
    if comskip is None:
        return None
    if logofinder_present and comskip.present:
        return "agree_present"
    if not logofinder_present and not comskip.present:
        return "agree_absent"
    return "conflict"


def timeline_record(point: TimelinePoint, comskip: ComskipPoint | None) -> dict:
    record = {
        "frame": point.frame,
        "time_seconds": round(point.time_seconds, 6),
        "logofinder_score": round(point.score, 9),
        "logofinder_present": point.present,
        "sample_kind": point.sample_kind,
        "comskip_good_edge": None,
        "comskip_present": None,
        "comskip_local_state_start": None,
        "comskip_local_state_end": None,
        "comskip_global_logo_percentage": None,
        "comskip_global_logo_enabled": None,
        "agreement": agreement(point.present, comskip),
    }
    if comskip is not None:
        record.update(
            {
                "comskip_good_edge": round(comskip.good_edge, 9),
                "comskip_present": comskip.present,
                "comskip_local_state_start": comskip.local_state_start,
                "comskip_local_state_end": comskip.local_state_end,
                "comskip_global_logo_percentage": round(comskip.global_logo_percentage, 9),
                "comskip_global_logo_enabled": comskip.global_logo_enabled,
            }
        )
    return record


def exact_transitions(points: Iterable[TimelinePoint]) -> list[dict]:
    ordered = sorted(points, key=lambda point: point.frame)
    transitions: list[dict] = []
    for left, right in zip(ordered, ordered[1:]):
        if right.frame == left.frame + 1 and left.present != right.present:
            transitions.append(
                {
                    "last_frame_before_change": left.frame,
                    "first_frame_after_change": right.frame,
                    "time_seconds": right.time_seconds,
                    "from_present": left.present,
                    "to_present": right.present,
                    "score_before": left.score,
                    "score_after": right.score,
                }
            )
    return transitions


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def run(args: argparse.Namespace) -> dict:
    video = args.video.resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    if args.sample_seconds <= 0:
        raise ValueError("--sample-seconds must be positive")
    if not 0 <= args.present_threshold <= 1:
        raise ValueError("--present-threshold must be between 0 and 1")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
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
        present_score,
    ) = load_internal_logo_api()

    probe = cv2.VideoCapture(str(video))
    if not probe.isOpened():
        raise RuntimeError(f"Could not open video {video}")
    fps = float(probe.get(cv2.CAP_PROP_FPS))
    total_frames = int(probe.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    probe.release()
    if fps <= 0 or total_frames <= 0:
        raise RuntimeError("Video has no usable FPS/frame-count metadata")
    duration_seconds = total_frames / fps
    learning_start = float(args.learning_start_seconds)
    learning_end = duration_seconds if args.learning_end_seconds is None else float(args.learning_end_seconds)
    if learning_start < 0 or learning_end > duration_seconds + 1.0 / fps or learning_end <= learning_start:
        raise ValueError("LogoFinder learning range must be inside the video and have positive length")

    started = time.perf_counter()
    overlay, reference, heatmap_times, reference_times, heatmap_seconds, reference_seconds = learn_overlay_in_range(
        video=video,
        start_seconds=learning_start,
        end_seconds=learning_end,
        heatmap_samples=args.heatmap_samples,
        reference_samples=args.reference_samples,
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
    if overlay is None:
        raise RuntimeError("LogoFinder heatmap did not produce a logo candidate")

    if reference is None:
        raise RuntimeError("LogoFinder could not build the median overlay reference")

    scorer = FrameScorer(cv2, video, reference, present_score)
    try:
        phase_started = time.perf_counter()
        if args.every_frame:
            timeline = scorer.score_every_frame(
                total_frames, fps=fps, threshold=args.present_threshold
            )
        else:
            timeline = build_timeline(
                total_frames=total_frames,
                fps=fps,
                sample_seconds=args.sample_seconds,
                score_at=scorer.score,
                threshold=args.present_threshold,
                sharp_delta=args.sharp_delta,
                subdivisions=args.refine_subdivisions,
            )
        timeline_seconds = time.perf_counter() - phase_started
        requested_frames = scorer.request_count
        seek_count = scorer.seek_count
        grab_count = scorer.grab_count
    finally:
        scorer.close()

    comskip = load_comskip_raw(args.comskip_raw.resolve() if args.comskip_raw else None)
    records = [timeline_record(point, comskip.get(point.frame)) for point in timeline]
    transitions = exact_transitions(timeline)
    write_jsonl(output_dir / "hybrid_logo_timeline.jsonl", records)
    write_jsonl(output_dir / "logofinder_transitions.jsonl", transitions)

    metadata = {
        "schema_version": 1,
        "video": str(video),
        "video_metadata": {
            "fps": fps,
            "total_frames": total_frames,
            "duration_seconds": total_frames / fps,
            "width": width,
            "height": height,
        },
        "logofinder": {
            "implementation": "comskip_internal_logo_sensor",
            "overlay": asdict(overlay),
            "heatmap_samples_requested": args.heatmap_samples,
            "reference_samples_requested": args.reference_samples,
            "learning_start_seconds": learning_start,
            "learning_end_seconds": learning_end,
            "heatmap_sample_seconds": heatmap_times,
            "reference_sample_seconds": reference_times,
            "present_threshold": args.present_threshold,
        },
        "timeline": {
            "mode": "every_decodable_frame" if args.every_frame else "coarse_to_fine",
            "coarse_step_seconds": (1.0 / fps) if args.every_frame else args.sample_seconds,
            "sharp_delta": args.sharp_delta,
            "refine_subdivisions": args.refine_subdivisions,
            "output_points": len(timeline),
            "requested_video_frames": requested_frames,
            "decoder_seeks": seek_count,
            "decoder_grabs_between_samples": grab_count,
            "exact_transitions": len(transitions),
        },
        "comskip_raw": str(args.comskip_raw.resolve()) if args.comskip_raw else None,
        "performance_seconds": {
            "heatmap_learning": heatmap_seconds,
            "median_reference": reference_seconds,
            "dense_timeline": timeline_seconds,
            "total": time.perf_counter() - started,
        },
    }
    (output_dir / "hybrid_logo_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def main() -> int:
    try:
        metadata = run(parse_args())
    except Exception as exc:
        print(f"hybrid-logo: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
