from __future__ import annotations

import json
import os
import shutil
import subprocess
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import cv2
    import numpy as np
except ModuleNotFoundError:
    cv2 = None
    np = None


SCHEMA_VERSION = "wedo-movies-breaks-v3"
CHANNEL_TOKEN = "wedo-movies"
NORMAL_LOGO_PRESENT = "PRESENT"
BUMPER_LOOKBACK_SECONDS = 25.0
BUMPER_ANALYSIS_WIDTH = 320
BUMPER_ANALYSIS_HEIGHT = 180
BUMPER_MIN_RED_FRACTION = 0.010
BUMPER_MAX_RED_FRACTION = 0.300
BUMPER_MIN_WHITE_FRACTION = 0.050
BUMPER_MAX_WHITE_FRACTION = 0.300
BUMPER_MIN_SCENE_CHANGE = 0.25
BUMPER_MIN_BACKTRACK_SECONDS = 5.0
BUMPER_MIN_LOGO_MASK_RECALL = 0.88


def _require_image_dependencies() -> None:
    if cv2 is None or np is None:
        raise RuntimeError("The WeDo red-layout scan requires bundled OpenCV and NumPy")


@dataclass(frozen=True)
class WedoMoviesConfig:
    sample_fps: float = 1.0
    analysis_width: int = 320
    analysis_height: int = 180
    top_band_end: float = 0.20
    bottom_band_start: float = 0.76
    min_top_red_fraction: float = 0.82
    min_bottom_red_fraction: float = 0.75
    max_missing_seconds: int = 3
    min_break_seconds: int = 90
    max_break_seconds: int = 135
    min_layout_samples: int = 90
    min_layout_coverage: float = 0.78
    boundary_lead_seconds: float = 1.0
    boundary_tail_seconds: float = 2.0
    max_program_hint_tail_seconds: float = 180.0


@dataclass(frozen=True)
class LayoutSample:
    second: int
    top_red_fraction: float
    bottom_red_fraction: float
    bottom_left_texture: float


@dataclass(frozen=True)
class WedoBreakCandidate:
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    first_layout_second: int
    last_layout_second: int
    layout_samples: int
    layout_coverage: float
    mean_top_red_fraction: float
    mean_bottom_red_fraction: float
    mean_bottom_left_texture: float
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class BrandedBumperCut:
    commercial_end_frame: int
    movie_start_frame: int
    scene_change_score: float
    red_fraction: float
    white_fraction: float
    logo_mask_recall: float


def is_wedo_movies_video(video: Path) -> bool:
    """The user's filename contract is exact and intentionally case-sensitive."""
    return CHANNEL_TOKEN in video.name


def _red_fraction(image: np.ndarray) -> float:
    _require_image_dependencies()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    low_red = cv2.inRange(hsv, (0, 90, 45), (12, 255, 255))
    high_red = cv2.inRange(hsv, (168, 90, 45), (179, 255, 255))
    red = cv2.bitwise_or(low_red, high_red)
    return float(np.count_nonzero(red)) / float(red.size)


def _bottom_left_texture(frame: np.ndarray) -> float:
    _require_image_dependencies()
    height, width = frame.shape[:2]
    crop = frame[int(height * 0.75):height, 0:int(width * 0.20)]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 160)
    white = float(np.count_nonzero(gray >= 205)) / gray.size
    dark = float(np.count_nonzero(gray <= 50)) / gray.size
    edge = float(np.count_nonzero(edges)) / edges.size
    return min(1.0, edge * 4.0) * min(1.0, white * 4.0) * min(1.0, dark * 4.0)


def layout_sample(frame: np.ndarray, second: int, config: WedoMoviesConfig) -> LayoutSample:
    height = frame.shape[0]
    top = frame[0:int(height * config.top_band_end)]
    bottom = frame[int(height * config.bottom_band_start):height]
    return LayoutSample(
        second=second,
        top_red_fraction=_red_fraction(top),
        bottom_red_fraction=_red_fraction(bottom),
        bottom_left_texture=_bottom_left_texture(frame),
    )


def is_layout_present(sample: LayoutSample, config: WedoMoviesConfig) -> bool:
    return (
        sample.top_red_fraction >= config.min_top_red_fraction
        and sample.bottom_red_fraction >= config.min_bottom_red_fraction
    )


def candidates_from_samples(
    samples: list[LayoutSample],
    *,
    duration_seconds: float,
    config: WedoMoviesConfig,
) -> list[WedoBreakCandidate]:
    positive = [sample for sample in samples if is_layout_present(sample, config)]
    groups: list[list[LayoutSample]] = []
    active: list[LayoutSample] = []
    for sample in positive:
        if active and sample.second - active[-1].second - 1 > config.max_missing_seconds:
            groups.append(active)
            active = []
        active.append(sample)
    if active:
        groups.append(active)

    candidates = []
    for group in groups:
        first = group[0].second
        last = group[-1].second
        measured_duration = last - first + 1
        coverage = len(group) / measured_duration
        if not config.min_break_seconds <= measured_duration <= config.max_break_seconds:
            continue
        if len(group) < config.min_layout_samples or coverage < config.min_layout_coverage:
            continue
        mean_top = float(np.mean([sample.top_red_fraction for sample in group]))
        mean_bottom = float(np.mean([sample.bottom_red_fraction for sample in group]))
        mean_texture = float(np.mean([sample.bottom_left_texture for sample in group]))
        start = max(0.0, first - config.boundary_lead_seconds)
        end = min(duration_seconds, last + 1 + config.boundary_tail_seconds)
        confidence = min(
            1.0,
            0.45 * coverage
            + 0.275 * min(1.0, mean_top / 0.90)
            + 0.275 * min(1.0, mean_bottom / 0.84),
        )
        candidates.append(
            WedoBreakCandidate(
                start_seconds=round(start, 6),
                end_seconds=round(end, 6),
                duration_seconds=round(end - start, 6),
                first_layout_second=first,
                last_layout_second=last,
                layout_samples=len(group),
                layout_coverage=round(coverage, 6),
                mean_top_red_fraction=round(mean_top, 6),
                mean_bottom_red_fraction=round(mean_bottom, 6),
                mean_bottom_left_texture=round(mean_texture, 6),
                confidence=round(confidence, 6),
                evidence=(
                    "fixed_red_top_band",
                    "fixed_red_bottom_band",
                    "approximately_two_minute_sequence",
                    "four_segments_with_short_ident_gaps",
                ),
            )
        )
    return candidates


def detect_wedo_movies_breaks(
    video: Path,
    *,
    ffmpeg: Path,
    duration_seconds: float,
    config: WedoMoviesConfig | None = None,
) -> dict:
    config = config or WedoMoviesConfig()
    _require_image_dependencies()
    if not is_wedo_movies_video(video):
        raise ValueError(f"WeDo Movies detector refused non-WeDo filename: {video.name}")
    command = [
        str(ffmpeg), "-v", "error", "-i", str(video), "-map", "0:v:0",
        "-an", "-sn", "-dn",
        "-vf", f"fps={config.sample_fps},scale={config.analysis_width}:{config.analysis_height}:flags=area",
        "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    frame_bytes = config.analysis_width * config.analysis_height * 3
    samples = []
    second = 0
    try:
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("FFmpeg pipes are unavailable")
        while True:
            payload = process.stdout.read(frame_bytes)
            if not payload:
                break
            if len(payload) != frame_bytes:
                raise RuntimeError("FFmpeg returned a truncated WeDo Movies analysis frame")
            frame = np.frombuffer(payload, dtype=np.uint8).reshape(
                (config.analysis_height, config.analysis_width, 3)
            )
            sample = layout_sample(frame, second, config)
            if is_layout_present(sample, config):
                samples.append(sample)
            second += 1
        process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        return_code = process.wait()
        process.stderr.close()
        if return_code != 0:
            raise RuntimeError(f"FFmpeg WeDo Movies scan failed with exit code {return_code}: {stderr.strip()}")
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise

    candidates = candidates_from_samples(
        samples,
        duration_seconds=duration_seconds,
        config=config,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "DETECTED" if candidates else "NO_BREAKS_FOUND",
        "channel": "WeDo Movies",
        "activation": {
            "matched": True,
            "rule": "case-sensitive filename substring",
            "token": CHANNEL_TOKEN,
            "filename": video.name,
        },
        "video": str(video),
        "duration_seconds": duration_seconds,
        "seconds_scanned": second,
        "positive_layout_samples": len(samples),
        "config": asdict(config),
        "candidates": [asdict(candidate) for candidate in candidates],
    }


def _normal_logo_present_spans(sidecar_path: Path) -> tuple[list[tuple[float, float]], str | None, int]:
    """Return spans detected by Comskip's selected recurring normal-logo mask."""
    spans: list[tuple[float, float]] = []
    active_start: float | None = None
    active_end: float | None = None
    reliability: str | None = None
    observations = 0

    with sidecar_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid hybrid-logo sidecar line {line_number}: {sidecar_path}"
                ) from exc
            if row.get("record_type") == "metadata":
                reliability = str(row.get("global_reliability", {}).get("comskip", "")) or None
                continue
            if row.get("record_type") != "observation":
                continue

            if row.get("comskip_frame") is None:
                continue
            observations += 1
            time_seconds = float(row["time_seconds"])
            present = row.get("comskip_local_state") == NORMAL_LOGO_PRESENT
            if present:
                if active_start is None:
                    active_start = time_seconds
                active_end = time_seconds
            elif active_start is not None and active_end is not None:
                spans.append((active_start, active_end))
                active_start = None
                active_end = None

    if active_start is not None and active_end is not None:
        spans.append((active_start, active_end))
    return spans, reliability, observations


def _bumper_frame_features(frame: np.ndarray) -> dict[str, float | bool | np.ndarray]:
    """Measure a centered WeDo self-promo slate without depending on its wording."""
    _require_image_dependencies()
    small = cv2.resize(
        frame,
        (BUMPER_ANALYSIS_WIDTH, BUMPER_ANALYSIS_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )
    height, width = small.shape[:2]
    center = small[int(height * 0.12):int(height * 0.88), int(width * 0.12):int(width * 0.88)]
    hsv = cv2.cvtColor(center, cv2.COLOR_BGR2HSV)
    low_red = cv2.inRange(hsv, (0, 105, 75), (12, 255, 255))
    high_red = cv2.inRange(hsv, (168, 105, 75), (179, 255, 255))
    red_fraction = float(np.count_nonzero(cv2.bitwise_or(low_red, high_red))) / float(low_red.size)
    white = cv2.inRange(hsv, (0, 0, 185), (179, 72, 255))
    white_fraction = float(np.count_nonzero(white)) / float(white.size)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    mean_luma = float(gray.mean())
    luma_deviation = float(gray.std())
    branded = (
        BUMPER_MIN_RED_FRACTION <= red_fraction <= BUMPER_MAX_RED_FRACTION
        and BUMPER_MIN_WHITE_FRACTION <= white_fraction <= BUMPER_MAX_WHITE_FRACTION
    )
    non_black = mean_luma >= 18.0 and luma_deviation >= 9.0
    return {
        "small": small,
        "gray": gray,
        "red_fraction": red_fraction,
        "white_fraction": white_fraction,
        "branded": branded,
        "non_black": non_black,
    }


def _load_logo_mask(path: Path) -> tuple[tuple[int, int, int, int], np.ndarray]:
    _require_image_dependencies()
    raw = path.read_bytes().decode("latin-1")
    values: dict[str, int] = {}
    for key in ("logoMinX", "logoMaxX", "logoMinY", "logoMaxY"):
        for line in raw.splitlines():
            if line.startswith(key + "="):
                values[key] = int(line.split("=", 1)[1])
                break
    if len(values) != 4:
        raise ValueError(f"Incomplete Comskip logo mask: {path}")
    marker = raw.find("\x82")
    if marker < 0:
        raise ValueError(f"Comskip logo mask has no combined mask: {path}")
    left, right = values["logoMinX"], values["logoMaxX"]
    top, bottom = values["logoMinY"], values["logoMaxY"]
    width = right - left + 1
    height = bottom - top + 1
    lines = raw[marker + 1:].lstrip("\r\n").splitlines()
    if len(lines) < height:
        raise ValueError(f"Truncated Comskip logo mask: {path}")
    mask = np.zeros((height, width), dtype=np.uint8)
    for y, line in enumerate(lines[:height]):
        for x, character in enumerate(line.ljust(width)[:width]):
            if character in "|-+":
                mask[y, x] = 255
    if int(np.count_nonzero(mask)) == 0:
        raise ValueError(f"Empty Comskip logo mask: {path}")
    return (left, top, right, bottom), mask


def _logo_mask_recall(
    frame: np.ndarray,
    logo_mask: tuple[tuple[int, int, int, int], np.ndarray],
) -> float:
    (left, top, right, bottom), mask = logo_mask
    crop = frame[top:bottom + 1, left:right + 1]
    if crop.shape[:2] != mask.shape:
        return 0.0
    gray = cv2.equalizeHist(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
    edges = cv2.Canny(gray, 25, 85)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    return float(np.count_nonzero(edges[mask > 0])) / float(np.count_nonzero(mask))


def _find_branded_bumper_cut(
    *,
    video_path: Path,
    fps: float,
    earliest_seconds: float,
    logo_return_seconds: float,
    logo_mask_path: Path,
    lookback_seconds: float = BUMPER_LOOKBACK_SECONDS,
) -> BrandedBumperCut | None:
    """Find a branded WeDo bumper cutting directly to a non-black movie frame.

    This deliberately does not backtrack to arbitrary scene changes.  A candidate
    needs the centered red/white WeDo self-promo signature immediately before the
    cut, a substantial full-frame change, and visible content immediately after it.
    """
    _require_image_dependencies()
    if fps <= 0 or lookback_seconds <= 0:
        return None
    start_seconds = max(earliest_seconds, logo_return_seconds - lookback_seconds)
    start_frame = max(0, int(round(start_seconds * fps)))
    stop_frame = max(start_frame, int(round(logo_return_seconds * fps)))
    logo_mask = _load_logo_mask(logo_mask_path)
    capture = cv2.VideoCapture(str(video_path))
    frames: list[tuple[int, np.ndarray, dict[str, float | bool | np.ndarray]]] = []
    try:
        if not capture.isOpened():
            return None
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        frame_number = start_frame
        while frame_number <= stop_frame:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            frames.append((frame_number, frame, _bumper_frame_features(frame)))
            frame_number += 1
    finally:
        capture.release()

    candidates: list[BrandedBumperCut] = []
    for index in range(len(frames) - 1):
        before_number, _before_frame, before = frames[index]
        after_number, after_frame, after = frames[index + 1]
        if not bool(before["branded"]) or not bool(after["non_black"]):
            continue
        backtrack_seconds = logo_return_seconds - (after_number / fps)
        if backtrack_seconds < BUMPER_MIN_BACKTRACK_SECONDS:
            continue
        before_gray = before["gray"]
        after_gray = after["gray"]
        scene_change = float(cv2.absdiff(before_gray, after_gray).mean()) / 255.0
        if scene_change < BUMPER_MIN_SCENE_CHANGE:
            continue
        logo_recall = _logo_mask_recall(after_frame, logo_mask)
        if logo_recall < BUMPER_MIN_LOGO_MASK_RECALL:
            continue
        confirmation_indices = [index + 1, min(len(frames) - 1, index + 4), min(len(frames) - 1, index + 9)]
        if sum(bool(frames[position][2]["non_black"]) for position in confirmation_indices) < 2:
            continue
        candidates.append(
            BrandedBumperCut(
                commercial_end_frame=before_number,
                movie_start_frame=after_number,
                scene_change_score=scene_change,
                red_fraction=float(before["red_fraction"]),
                white_fraction=float(before["white_fraction"]),
                logo_mask_recall=logo_recall,
            )
        )
    return candidates[-1] if candidates else None


def extend_wedo_movies_program_hint_tails(
    report: dict,
    *,
    sidecar_path: Path,
    max_tail_seconds: float = 180.0,
    video_path: Path | None = None,
    fps: float | None = None,
    logo_mask_path: Path | None = None,
) -> dict:
    """Extend anchored WeDo breaks until the normal movie logo first returns."""
    if max_tail_seconds <= 0:
        raise ValueError("WeDo Movies program-hint tail limit must be positive")
    if not report.get("activation", {}).get("matched"):
        raise ValueError("WeDo Movies tail extension refused a non-WeDo report")

    extended_report = deepcopy(report)
    candidates = extended_report.get("candidates", [])
    spans, reliability, observations = _normal_logo_present_spans(sidecar_path)
    sensor_unavailable = observations == 0 or reliability == "REJECTED_BY_EXISTING_GATE"
    duration_seconds = float(extended_report["duration_seconds"])
    extended_count = 0

    for candidate in candidates:
        original_end = float(candidate["end_seconds"])
        layout_end = min(duration_seconds, float(candidate["last_layout_second"]) + 1.0)
        scan_limit = min(duration_seconds, layout_end + max_tail_seconds)
        logo_return = None
        reason = "LOGO_SENSOR_UNAVAILABLE"
        new_end = original_end

        if not sensor_unavailable:
            reason = "MAXIMUM_TAIL_REACHED"
            for span_start, span_end in spans:
                if span_end < layout_end:
                    continue
                if span_start > scan_limit:
                    break
                logo_return = max(layout_end, span_start)
                reason = "NORMAL_MOVIE_LOGO_RETURNED"
                break
            new_end = logo_return if logo_return is not None else scan_limit
            bumper_cut = None
            if (
                logo_return is not None
                and video_path is not None
                and fps is not None
                and logo_mask_path is not None
            ):
                bumper_cut = _find_branded_bumper_cut(
                    video_path=video_path,
                    fps=fps,
                    earliest_seconds=original_end,
                    logo_return_seconds=logo_return,
                    logo_mask_path=logo_mask_path,
                )
                if bumper_cut is not None:
                    new_end = bumper_cut.commercial_end_frame / fps
                    reason = "BRANDED_WEDO_BUMPER_TO_MOVIE_CUT"
            new_end = max(original_end, new_end)

        new_end = min(duration_seconds, new_end)
        extension_seconds = max(0.0, new_end - original_end)
        if extension_seconds > 0:
            extended_count += 1
        candidate["end_seconds"] = round(new_end, 6)
        candidate["duration_seconds"] = round(new_end - float(candidate["start_seconds"]), 6)
        candidate["program_hint_tail"] = {
            "status": "SKIPPED" if sensor_unavailable else "APPLIED",
            "reason": reason,
            "layout_end_seconds": round(layout_end, 6),
            "original_end_seconds": round(original_end, 6),
            "scan_limit_seconds": round(scan_limit, 6),
            "normal_logo_return_seconds": round(logo_return, 6) if logo_return is not None else None,
            "extended_end_seconds": round(new_end, 6),
            "extension_seconds": round(extension_seconds, 6),
        }
        if (
            not sensor_unavailable
            and logo_return is not None
            and video_path is not None
            and fps is not None
            and logo_mask_path is not None
        ):
            candidate["program_hint_tail"]["bumper_refinement"] = (
                {
                    "status": "APPLIED",
                    "commercial_end_frame": bumper_cut.commercial_end_frame,
                    "movie_start_frame": bumper_cut.movie_start_frame,
                    "scene_change_score": round(bumper_cut.scene_change_score, 6),
                    "red_fraction": round(bumper_cut.red_fraction, 6),
                    "white_fraction": round(bumper_cut.white_fraction, 6),
                    "logo_mask_recall": round(bumper_cut.logo_mask_recall, 6),
                }
                if bumper_cut is not None
                else {"status": "NO_UNAMBIGUOUS_BRANDED_BUMPER_CUT"}
            )

    extended_report["tail_extension"] = {
        "status": "SKIPPED_LOGO_SENSOR_UNAVAILABLE" if sensor_unavailable else "APPLIED",
        "strategy": "first_local_normal_logo_presence_with_conservative_branded_bumper_backtrack",
        "post_detection_hold_seconds": 0,
        "max_tail_seconds": max_tail_seconds,
        "bumper_backtrack_seconds": BUMPER_LOOKBACK_SECONDS,
        "bumper_minimum_backtrack_seconds": BUMPER_MIN_BACKTRACK_SECONDS,
        "bumper_minimum_logo_mask_recall": BUMPER_MIN_LOGO_MASK_RECALL,
        "logo_sensor_reliability": reliability,
        "logo_observations": observations,
        "normal_logo_present_spans": len(spans),
        "candidate_count": len(candidates),
        "extended_candidate_count": extended_count,
    }
    return extended_report


def _parse_txt(path: Path) -> tuple[str, int, list[tuple[int, int]]]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if not lines or not lines[0].startswith("FILE PROCESSING COMPLETE "):
        raise RuntimeError(f"Cannot fuse incomplete Comskip TXT: {path}")
    parts = lines[0].split()
    total_frames = int(parts[3])
    intervals = []
    for line in lines[2:]:
        fields = line.split()
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            intervals.append((int(fields[0]), int(fields[1])))
    return lines[0], total_frames, intervals


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def apply_wedo_movies_intervals(
    *,
    txt_path: Path,
    edl_path: Path,
    report: dict,
    fps: float,
    authoritative: bool = False,
) -> dict:
    header, total_frames, existing = _parse_txt(txt_path)
    added = []
    for candidate in report.get("candidates", []):
        start = max(0, min(total_frames, int(round(float(candidate["start_seconds"]) * fps))))
        end = max(start, min(total_frames, int(round(float(candidate["end_seconds"]) * fps))))
        added.append((start, end))
    if authoritative:
        # WeDo Movies is a closed station profile.  General Comskip intervals
        # may provide a harmless outer crop at the physical file edges, but
        # they must never add an internal block or extend a WeDo interval.
        edge_existing = [
            interval
            for interval in existing
            if (interval[0] <= 3 or interval[1] >= total_frames - 2)
            and not any(
                max(interval[0], wedo[0]) <= min(interval[1], wedo[1])
                for wedo in added
            )
        ]
        merged = _merge_intervals([*edge_existing, *added])
    else:
        edge_existing = []
        merged = _merge_intervals([*existing, *added])

    pre_txt = txt_path.with_name(txt_path.stem + "-pre-wedo.txt")
    pre_edl = edl_path.with_name(edl_path.stem + "-pre-wedo.edl")
    shutil.copy2(txt_path, pre_txt)
    if edl_path.is_file():
        shutil.copy2(edl_path, pre_edl)

    txt_payload = header + "\n-------------------\n"
    txt_payload += "".join(f"{start}\t{end}\n" for start, end in merged)
    edl_payload = "".join(f"{start / fps:.3f}\t{end / fps:.3f}\t0\n" for start, end in merged)
    txt_temporary = txt_path.with_name(txt_path.name + ".wedo.tmp")
    edl_temporary = edl_path.with_name(edl_path.name + ".wedo.tmp")
    try:
        txt_temporary.write_text(txt_payload, encoding="ascii", newline="\n")
        edl_temporary.write_text(edl_payload, encoding="ascii", newline="\n")
        os.replace(edl_temporary, edl_path)
        os.replace(txt_temporary, txt_path)
    except BaseException:
        txt_temporary.unlink(missing_ok=True)
        edl_temporary.unlink(missing_ok=True)
        shutil.copy2(pre_txt, txt_path)
        if pre_edl.is_file():
            shutil.copy2(pre_edl, edl_path)
        else:
            edl_path.unlink(missing_ok=True)
        raise
    return {
        "existing_intervals": [list(interval) for interval in existing],
        "wedo_intervals": [list(interval) for interval in added],
        "fused_intervals": [list(interval) for interval in merged],
        "authoritative": authoritative,
        "preserved_outer_intervals": [list(interval) for interval in edge_existing],
        "pre_wedo_txt": str(pre_txt),
        "pre_wedo_edl": str(pre_edl) if pre_edl.is_file() else None,
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
