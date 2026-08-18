from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


UNAVAILABLE_LOGOFINDER_SCORE = 0.42


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
    parser.add_argument("--ffmpeg", type=Path)
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
        overlay_present_score_from_crop,
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
        overlay_present_score_from_crop,
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
        return None, None, heatmap_times, [], heatmap_seconds, 0.0, {
            "heatmap_frames_decoded": 0,
            "reference_frames_decoded": 0,
        }
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
            return overlay, None, heatmap_times, reference_times, heatmap_seconds, time.perf_counter() - reference_started, {
                "heatmap_frames_decoded": best.frame_count,
                "reference_frames_decoded": 0,
            }
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
        return overlay, None, heatmap_times, reference_times, heatmap_seconds, time.perf_counter() - reference_started, {
            "heatmap_frames_decoded": best.frame_count,
            "reference_frames_decoded": len(crops),
        }
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
        {
            "heatmap_frames_decoded": best.frame_count,
            "reference_frames_decoded": len(crops),
        },
    )


class FrameScorer:
    def __init__(
        self,
        cv2,
        np,
        video: Path,
        reference,
        score_function: Callable,
        crop_score_function: Callable | None = None,
        exit_trace: Callable[..., None] | None = None,
    ):
        self._cv2 = cv2
        self._np = np
        self._video = video
        self._capture = None
        self._reference = reference
        self._score_function = score_function
        self._crop_score_function = crop_score_function
        self._exit_trace = exit_trace or (lambda _stage, **_details: None)
        self._cache: dict[int, float] = {}
        self.request_count = 0
        self.seek_count = 0
        self.grab_count = 0
        self.decode_seconds = 0.0
        self.score_seconds = 0.0
        self.score_timings: dict[str, float] = {}
        self.video_open_count = 0
        self.full_frame_decodes = 0
        self.roi_decodes = 0

    def _ensure_capture(self):
        if self._capture is None:
            self._capture = self._cv2.VideoCapture(str(self._video))
            self.video_open_count += 1
            if not self._capture.isOpened():
                raise RuntimeError(f"Could not open video {self._video}")
        return self._capture

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def score(self, frame: int) -> float:
        frame = int(frame)
        cached = self._cache.get(frame)
        if cached is not None:
            return cached
        capture = self._ensure_capture()
        position = int(round(capture.get(self._cv2.CAP_PROP_POS_FRAMES)))
        forward_distance = frame - position
        if 0 <= forward_distance <= 250:
            while position < frame:
                if not capture.grab():
                    raise RuntimeError(f"Could not advance to frame {frame}")
                position += 1
                self.grab_count += 1
        else:
            capture.set(self._cv2.CAP_PROP_POS_FRAMES, frame)
            self.seek_count += 1
        started = time.perf_counter()
        ok, image = capture.read()
        self.decode_seconds += time.perf_counter() - started
        if not ok or image is None:
            raise RuntimeError(f"Could not decode frame {frame}")
        self.full_frame_decodes += 1
        started = time.perf_counter()
        value = float(self._score_function(self._reference, image))
        self.score_seconds += time.perf_counter() - started
        self._cache[frame] = value
        self.request_count += 1
        return value

    @staticmethod
    def _read_exact(stream, buffer: bytearray) -> bool:
        view = memoryview(buffer)
        offset = 0
        while offset < len(buffer):
            count = stream.readinto(view[offset:])
            if not count:
                return False
            offset += count
        return True

    def _score_every_frame_ffmpeg(
        self,
        maximum_frames: int,
        *,
        fps: float,
        threshold: float,
        ffmpeg: Path,
    ) -> list[TimelinePoint]:
        if self._crop_score_function is None:
            raise RuntimeError("No crop score function is configured")
        left, top, right, bottom = self._reference.overlay.rect
        width = right - left
        height = bottom - top
        command = [
            str(ffmpeg),
            "-v", "error",
            "-i", str(self._video),
            "-map", "0:v:0",
            "-an", "-sn", "-dn",
            "-vf", f"format=bgr24,crop={width}:{height}:{left}:{top}",
            "-frames:v", str(maximum_frames),
            "-vsync", "0",
            "-pix_fmt", "bgr24",
            "-f", "rawvideo",
            "pipe:1",
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        self._exit_trace("ROI_FFMPEG_STARTED", pid=process.pid)
        self.video_open_count += 1
        frame_bytes = bytearray(width * height * 3)
        points: list[TimelinePoint] = []
        try:
            if process.stdout is None or process.stderr is None:
                raise RuntimeError("FFmpeg ROI decoder pipes are unavailable")
            for frame in range(maximum_frames):
                started = time.perf_counter()
                complete = self._read_exact(process.stdout, frame_bytes)
                self.decode_seconds += time.perf_counter() - started
                if not complete:
                    break
                image = self._np.frombuffer(frame_bytes, dtype=self._np.uint8).reshape(
                    (height, width, 3)
                )
                started = time.perf_counter()
                value = float(
                    self._crop_score_function(
                        self._reference,
                        image,
                        self.score_timings,
                    )
                )
                self.score_seconds += time.perf_counter() - started
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
                self.roi_decodes += 1
            process.stdout.close()
            self._exit_trace("ROI_FFMPEG_STDOUT_CLOSED", pid=process.pid)
            self._exit_trace("ROI_FFMPEG_STDERR_READ_START", pid=process.pid)
            stderr = process.stderr.read().decode("utf-8", errors="replace")
            self._exit_trace("ROI_FFMPEG_STDERR_READ_END", pid=process.pid, bytes=len(stderr.encode("utf-8")))
            self._exit_trace("ROI_FFMPEG_WAIT_START", pid=process.pid)
            return_code = process.wait()
            self._exit_trace("ROI_FFMPEG_WAIT_END", pid=process.pid, return_code=return_code)
            process.stderr.close()
            self._exit_trace("ROI_FFMPEG_STDERR_CLOSED", pid=process.pid)
            if return_code != 0:
                raise RuntimeError(
                    f"FFmpeg ROI decoder failed with exit code {return_code}: {stderr.strip()}"
                )
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
        return points

    def score_every_frame(
        self,
        maximum_frames: int,
        *,
        fps: float,
        threshold: float,
        ffmpeg: Path | None = None,
    ) -> list[TimelinePoint]:
        """Decode sequentially and apply only the already learned crop scorer."""
        if ffmpeg is not None and ffmpeg.is_file():
            return self._score_every_frame_ffmpeg(
                maximum_frames,
                fps=fps,
                threshold=threshold,
                ffmpeg=ffmpeg,
            )
        capture = self._ensure_capture()
        points: list[TimelinePoint] = []
        capture.set(self._cv2.CAP_PROP_POS_FRAMES, 0)
        for frame in range(maximum_frames):
            started = time.perf_counter()
            ok, image = capture.read()
            self.decode_seconds += time.perf_counter() - started
            if not ok or image is None:
                break
            self.full_frame_decodes += 1
            started = time.perf_counter()
            value = float(self._score_function(self._reference, image))
            self.score_seconds += time.perf_counter() - started
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


def unavailable_timeline(total_frames: int, fps: float) -> list[TimelinePoint]:
    """Represent an attempted but unavailable sensor without inventing evidence."""
    return [
        TimelinePoint(
            frame=frame,
            time_seconds=frame / fps,
            score=UNAVAILABLE_LOGOFINDER_SCORE,
            present=False,
            sample_kind="frame",
        )
        for frame in range(total_frames)
    ]


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
        crop_present_score,
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
    (
        overlay,
        reference,
        heatmap_times,
        reference_times,
        heatmap_seconds,
        reference_seconds,
        learning_profile,
    ) = learn_overlay_in_range(
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
    unavailable_reason = None
    if overlay is None:
        unavailable_reason = "heatmap_no_logo_candidate"
    elif reference is None:
        unavailable_reason = "median_reference_unavailable"

    if unavailable_reason is not None:
        phase_started = time.perf_counter()
        timeline = unavailable_timeline(total_frames, fps)
        timeline_seconds = time.perf_counter() - phase_started
        requested_frames = 0
        seek_count = 0
        grab_count = 0
        decoder_seconds = 0.0
        score_seconds = 0.0
        score_timings: dict[str, float] = {}
        timeline_video_opens = 0
        full_frame_decodes = 0
        roi_decodes = 0
    else:
        scorer = FrameScorer(
            cv2,
            np,
            video,
            reference,
            present_score,
            crop_present_score,
            getattr(args, "exit_trace", None),
        )
        try:
            phase_started = time.perf_counter()
            if args.every_frame:
                timeline = scorer.score_every_frame(
                    total_frames,
                    fps=fps,
                    threshold=args.present_threshold,
                    ffmpeg=getattr(args, "ffmpeg", None),
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
            decoder_seconds = scorer.decode_seconds
            score_seconds = scorer.score_seconds
            score_timings = dict(scorer.score_timings)
            timeline_video_opens = scorer.video_open_count
            full_frame_decodes = scorer.full_frame_decodes
            roi_decodes = scorer.roi_decodes
        finally:
            scorer.close()

    postprocess_started = time.perf_counter()
    phase_started = time.perf_counter()
    comskip = load_comskip_raw(args.comskip_raw.resolve() if args.comskip_raw else None)
    comskip_load_seconds = time.perf_counter() - phase_started
    phase_started = time.perf_counter()
    records = [timeline_record(point, comskip.get(point.frame)) for point in timeline]
    record_build_seconds = time.perf_counter() - phase_started
    phase_started = time.perf_counter()
    transitions = exact_transitions(timeline)
    transition_build_seconds = time.perf_counter() - phase_started
    phase_started = time.perf_counter()
    write_jsonl(output_dir / "hybrid_logo_timeline.jsonl", records)
    timeline_write_seconds = time.perf_counter() - phase_started
    phase_started = time.perf_counter()
    write_jsonl(output_dir / "logofinder_transitions.jsonl", transitions)
    transition_write_seconds = time.perf_counter() - phase_started
    postprocess_seconds = time.perf_counter() - postprocess_started

    score_operation_seconds = sum(score_timings.values())
    timeline_python_seconds = max(
        0.0,
        timeline_seconds - decoder_seconds - score_operation_seconds,
    )
    learning_decoded_frames = (
        learning_profile["heatmap_frames_decoded"]
        + learning_profile["reference_frames_decoded"]
    )

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
            "status": "UNAVAILABLE" if unavailable_reason else "AVAILABLE",
            "unavailable_reason": unavailable_reason,
            "overlay": asdict(overlay) if overlay is not None else {"confidence": 0.0},
            "heatmap_samples_requested": args.heatmap_samples,
            "reference_samples_requested": args.reference_samples,
            "learning_start_seconds": learning_start,
            "learning_end_seconds": learning_end,
            "heatmap_sample_seconds": heatmap_times,
            "reference_sample_seconds": reference_times,
            "present_threshold": args.present_threshold,
        },
        "timeline": {
            "mode": (
                "unavailable_framewise"
                if unavailable_reason
                else "every_decodable_frame"
                if args.every_frame
                else "coarse_to_fine"
            ),
            "coarse_step_seconds": (1.0 / fps) if args.every_frame else args.sample_seconds,
            "sharp_delta": args.sharp_delta,
            "refine_subdivisions": args.refine_subdivisions,
            "output_points": len(timeline),
            "requested_video_frames": requested_frames,
            "decoder_seeks": seek_count,
            "decoder_grabs_between_samples": grab_count,
            "exact_transitions": len(transitions),
        },
        "profile_counts": {
            "video_open_operations": 1 + (1 if heatmap_times else 0) + (1 if reference_times else 0) + timeline_video_opens,
            "seek_operations": len(heatmap_times) + len(reference_times) + seek_count,
            "decoded_frames": learning_decoded_frames + requested_frames,
            "learning_frames_decoded": learning_decoded_frames,
            "timeline_frames_decoded": requested_frames,
            "frames_analyzed": requested_frames,
            "frames_with_logo_score": requested_frames,
            "full_frame_video_decodes": learning_decoded_frames + full_frame_decodes,
            "full_frame_image_operations_after_learning": full_frame_decodes,
            "roi_image_operations_after_learning": roi_decodes,
            "correlation_calculations": requested_frames * 2,
        },
        "comskip_raw": str(args.comskip_raw.resolve()) if args.comskip_raw else None,
        "performance_seconds": {
            "heatmap_learning": heatmap_seconds,
            "median_reference": reference_seconds,
            "dense_timeline": timeline_seconds,
            "video_decoding_and_roi_pipe": decoder_seconds,
            "score_total": score_seconds,
            "score_operations": score_timings,
            "score_python_and_timeline_overhead": timeline_python_seconds,
            "comskip_csv_read": comskip_load_seconds,
            "timeline_record_build": record_build_seconds,
            "transition_build": transition_build_seconds,
            "timeline_jsonl_write": timeline_write_seconds,
            "transition_jsonl_write": transition_write_seconds,
            "postprocess_total": postprocess_seconds,
            "total": time.perf_counter() - started,
        },
    }
    (output_dir / "hybrid_logo_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    getattr(args, "exit_trace", lambda _stage, **_details: None)(
        "HYBRID_LOGO_ANALYSIS_RUN_RETURN"
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
