from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


SAMPLE_ZONE_WIDTH = 420
MIN_FRAMES = 12
EDGE_FREQUENCY_THRESHOLD = 0.28
HEAT_PERCENTILE = 96.5
MIN_AREA_RATIO = 0.00018
MAX_AREA_RATIO = 0.018
MIN_WIDTH_RATIO = 0.010
MAX_WIDTH_RATIO = 0.190
MIN_HEIGHT_RATIO = 0.010
MAX_HEIGHT_RATIO = 0.170
MAX_ASPECT_RATIO = 4.5
MAX_BORDER_TOUCH_RATIO = 0.58
EXPAND_FACTOR = 0.28
SUBCOMPONENT_EDGE_FREQUENCY_THRESHOLD = 0.14
SUBCOMPONENT_HEAT_PERCENTILE = 88.0
MIN_SUBCOMPONENT_AREA = 18
MAX_SUBCOMPONENT_STRIP_ASPECT = 6.0
MAX_SUBCOMPONENT_STRIP_WIDTH_RATIO = 0.45


@dataclass(frozen=True)
class ProgramOverlay:
    rect: tuple[int, int, int, int]
    source: str
    confidence: float
    sample_count: int


@dataclass(frozen=True)
class OverlayReference:
    overlay: ProgramOverlay
    gray: np.ndarray
    edges: np.ndarray
    edge_mask: np.ndarray
    template_mask: np.ndarray


@dataclass(frozen=True)
class LogoSearchZone:
    name: str
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class LogoHeatmapCandidate:
    zone_name: str
    rect: tuple[int, int, int, int]
    score: float
    heat: float
    edge_frequency: float
    mean_edge_density: float
    frame_count: int
    sample_times: tuple[str, ...]


LOGO_SEARCH_ZONES = (
    LogoSearchZone("oben_rechts", (0.55, 0.00, 1.00, 0.35)),
    LogoSearchZone("oben_links", (0.00, 0.00, 0.45, 0.35)),
    LogoSearchZone("unten_rechts", (0.55, 0.65, 1.00, 1.00)),
    LogoSearchZone("unten_links", (0.00, 0.65, 0.45, 1.00)),
)


def seconds_to_display(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def read_frame_at(capture: cv2.VideoCapture, seconds: float):
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
    except Exception:
        return None
    return frame if ok and frame is not None else None


def scale_zone_rect(zone: LogoSearchZone, frame_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = frame_size
    left, top, right, bottom = zone.rect
    return (
        max(0, min(width - 1, int(round(left * width)))),
        max(0, min(height - 1, int(round(top * height)))),
        max(1, min(width, int(round(right * width)))),
        max(1, min(height, int(round(bottom * height)))),
    )


def resize_zone(zone_bgr: np.ndarray) -> tuple[np.ndarray, float]:
    height, width = zone_bgr.shape[:2]
    if width <= SAMPLE_ZONE_WIDTH:
        return zone_bgr, 1.0
    scale = SAMPLE_ZONE_WIDTH / width
    return cv2.resize(
        zone_bgr,
        (SAMPLE_ZONE_WIDTH, max(1, int(height * scale))),
        interpolation=cv2.INTER_AREA,
    ), scale


def normalize_float(image: np.ndarray) -> np.ndarray:
    image = image.astype(np.float32)
    minimum = float(image.min())
    maximum = float(image.max())
    if maximum - minimum < 1e-6:
        return np.zeros(image.shape, dtype=np.float32)
    return (image - minimum) / (maximum - minimum)


def stack_heatmap(zone_frames: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    gray_frames = []
    edge_frames = []
    for frame in zone_frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        gray_frames.append(gray.astype(np.float32))
        edge_frames.append((cv2.Canny(gray, 35, 110) > 0).astype(np.float32))
    gray_stack = np.stack(gray_frames)
    edge_stack = np.stack(edge_frames)
    mean_gray = np.clip(gray_stack.mean(axis=0), 0, 255).astype(np.uint8)
    mean_edges = (cv2.Canny(mean_gray, 25, 85) > 0).astype(np.float32)
    edge_frequency = edge_stack.mean(axis=0)
    temporal_std = gray_stack.std(axis=0)
    inverse_motion = normalize_float(255.0 - np.clip(temporal_std * 10.0, 0, 255))
    heat = normalize_float(edge_frequency) * 0.45 + mean_edges * 0.35 + inverse_motion * 0.20
    return heat, edge_frequency, mean_edges


def component_border_touch(rect: tuple[int, int, int, int], image_size: tuple[int, int]) -> float:
    left, top, width, height = rect
    image_width, image_height = image_size
    touch = 0
    if left <= 1:
        touch += height
    if top <= 1:
        touch += width
    if left + width >= image_width - 1:
        touch += height
    if top + height >= image_height - 1:
        touch += width
    return touch / max(1, 2 * width + 2 * height)


def remove_long_horizontal_lines(mask: np.ndarray) -> np.ndarray:
    _height, width = mask.shape[:2]
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(18, int(width * 0.62)), 3))
    long_lines = cv2.morphologyEx(mask, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    cleaned = mask.copy()
    cleaned[long_lines > 0] = 0
    return cleaned


def remove_strip_like_components(mask: np.ndarray, parent_size: tuple[int, int]) -> np.ndarray:
    parent_width, _parent_height = parent_size
    component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    filtered = np.zeros(mask.shape, dtype=np.uint8)
    for component_id in range(1, component_count):
        _left, _top, width, height, area = [int(value) for value in stats[component_id]]
        if area < MIN_SUBCOMPONENT_AREA:
            continue
        aspect = max(width / max(1, height), height / max(1, width))
        is_wide_strip = width > parent_width * MAX_SUBCOMPONENT_STRIP_WIDTH_RATIO and aspect > MAX_SUBCOMPONENT_STRIP_ASPECT
        is_thin_line = height <= 3 and width > 16
        if is_wide_strip or is_thin_line:
            continue
        filtered[labels == component_id] = 255
    return filtered


def expand_rect(rect: tuple[int, int, int, int], frame_size: tuple[int, int]) -> tuple[int, int, int, int]:
    frame_width, frame_height = frame_size
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    pad_x = max(6, int(width * EXPAND_FACTOR))
    pad_y = max(6, int(height * EXPAND_FACTOR))
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(frame_width, right + pad_x),
        min(frame_height, bottom + pad_y),
    )


def zone_multiplier(zone_name: str) -> float:
    return {"oben_rechts": 1.10, "oben_links": 1.06, "unten_rechts": 0.92, "unten_links": 0.72}.get(zone_name, 1.0)


def candidate_from_component(
    *,
    zone_name: str,
    rect: tuple[int, int, int, int],
    component_mask: np.ndarray,
    heat: np.ndarray,
    edge_frequency: np.ndarray,
    mean_edges: np.ndarray,
    scale: float,
    zone_offset: tuple[int, int],
    full_frame_size: tuple[int, int],
    frame_count: int,
    sample_times: tuple[str, ...],
) -> LogoHeatmapCandidate | None:
    left, top, width, height = rect
    frame_width, frame_height = full_frame_size
    scaled_full_width = max(1, int(frame_width * scale))
    scaled_full_height = max(1, int(frame_height * scale))
    area = int(np.count_nonzero(component_mask))
    area_ratio = area / max(1, scaled_full_width * scaled_full_height)
    width_ratio = width / scaled_full_width
    height_ratio = height / scaled_full_height
    if not (MIN_AREA_RATIO <= area_ratio <= MAX_AREA_RATIO):
        return None
    if not (MIN_WIDTH_RATIO <= width_ratio <= MAX_WIDTH_RATIO):
        return None
    if not (MIN_HEIGHT_RATIO <= height_ratio <= MAX_HEIGHT_RATIO):
        return None
    aspect = max(width_ratio / max(0.001, height_ratio), height_ratio / max(0.001, width_ratio))
    if aspect > MAX_ASPECT_RATIO or component_border_touch(rect, (heat.shape[1], heat.shape[0])) > MAX_BORDER_TOUCH_RATIO:
        return None
    mask = component_mask > 0
    component_heat = float(heat[mask].mean())
    component_edge_frequency = float(edge_frequency[mask].mean())
    component_mean_edges = float(mean_edges[mask].mean())
    compactness = 1.0 - min(1.0, (aspect - 1.0) / (MAX_ASPECT_RATIO - 1.0))
    size_score = 1.0 - min(1.0, abs(area_ratio - 0.0045) / 0.014)
    score = (
        component_heat * 0.45
        + component_edge_frequency * 0.28
        + component_mean_edges * 0.12
        + compactness * 0.08
        + size_score * 0.07
    ) * zone_multiplier(zone_name)
    inverse_scale = 1.0 / scale
    zone_left, zone_top = zone_offset
    full_rect = expand_rect(
        (
            zone_left + int(round(left * inverse_scale)),
            zone_top + int(round(top * inverse_scale)),
            zone_left + int(round((left + width) * inverse_scale)),
            zone_top + int(round((top + height) * inverse_scale)),
        ),
        full_frame_size,
    )
    return LogoHeatmapCandidate(
        zone_name, full_rect, score, component_heat, component_edge_frequency,
        component_mean_edges, frame_count, sample_times,
    )


def extract_subcomponent_candidates(
    *,
    zone_name: str,
    rect: tuple[int, int, int, int],
    component_mask: np.ndarray,
    heat: np.ndarray,
    edge_frequency: np.ndarray,
    mean_edges: np.ndarray,
    scale: float,
    zone_offset: tuple[int, int],
    full_frame_size: tuple[int, int],
    frame_count: int,
    sample_times: tuple[str, ...],
) -> list[LogoHeatmapCandidate]:
    left, top, width, height = rect
    if width <= 2 or height <= 2:
        return []
    base_mask = component_mask[top : top + height, left : left + width] > 0
    if int(np.count_nonzero(base_mask)) < MIN_SUBCOMPONENT_AREA:
        return []
    heat_roi = heat[top : top + height, left : left + width]
    edge_roi = edge_frequency[top : top + height, left : left + width]
    mean_edges_roi = mean_edges[top : top + height, left : left + width]
    strength = normalize_float(edge_roi) * 0.45 + mean_edges_roi * 0.35 + normalize_float(heat_roi) * 0.20
    values = strength[base_mask]
    if values.size == 0:
        return []
    threshold = max(float(np.percentile(values, SUBCOMPONENT_HEAT_PERCENTILE)), 0.22)
    sub_binary = (
        base_mask
        & ((strength >= threshold) | (edge_roi >= SUBCOMPONENT_EDGE_FREQUENCY_THRESHOLD) | (mean_edges_roi > 0))
    ).astype(np.uint8) * 255
    sub_binary = remove_long_horizontal_lines(sub_binary)
    sub_binary = remove_strip_like_components(sub_binary, (width, height))
    sub_binary = cv2.morphologyEx(
        sub_binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 7)),
        iterations=1,
    )
    sub_binary = cv2.dilate(sub_binary, np.ones((2, 2), np.uint8), iterations=1)
    component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(sub_binary, connectivity=8)
    candidates = []
    for component_id in range(1, component_count):
        sub_left, sub_top, sub_width, sub_height, sub_area = [int(value) for value in stats[component_id]]
        if sub_area < MIN_SUBCOMPONENT_AREA:
            continue
        sub_mask = np.zeros(component_mask.shape, dtype=np.uint8)
        sub_mask[top + sub_top : top + sub_top + sub_height, left + sub_left : left + sub_left + sub_width] = (
            labels[sub_top : sub_top + sub_height, sub_left : sub_left + sub_width] == component_id
        ).astype(np.uint8) * 255
        candidate = candidate_from_component(
            zone_name=zone_name,
            rect=(left + sub_left, top + sub_top, sub_width, sub_height),
            component_mask=sub_mask,
            heat=heat,
            edge_frequency=edge_frequency,
            mean_edges=mean_edges,
            scale=scale,
            zone_offset=zone_offset,
            full_frame_size=full_frame_size,
            frame_count=frame_count,
            sample_times=sample_times,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def detect_logo_by_heatmap(
    *,
    video_path: Path,
    sample_count: int,
    max_candidates: int,
    seconds_list: list[int],
) -> list[LogoHeatmapCandidate]:
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            return []
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            return []
        frames_with_times = []
        for second in seconds_list:
            frame = read_frame_at(capture, second)
            if frame is not None:
                frames_with_times.append((second, frame))
        if len(frames_with_times) < MIN_FRAMES:
            return []
        frame_size = (width, height)
        sample_times = tuple(seconds_to_display(second) for second, _frame in frames_with_times)
        candidates = []
        for zone in LOGO_SEARCH_ZONES:
            zone_left, zone_top, zone_right, zone_bottom = scale_zone_rect(zone, frame_size)
            if zone_right <= zone_left or zone_bottom <= zone_top:
                continue
            resized_frames = []
            scale = 1.0
            for _second, frame in frames_with_times:
                resized, scale = resize_zone(frame[zone_top:zone_bottom, zone_left:zone_right])
                resized_frames.append(resized)
            heat, edge_frequency, mean_edges = stack_heatmap(resized_frames)
            threshold = max(EDGE_FREQUENCY_THRESHOLD, float(np.percentile(heat, HEAT_PERCENTILE)))
            binary = (heat >= threshold).astype(np.uint8) * 255
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)
            binary = cv2.dilate(binary, np.ones((3, 3), np.uint8), iterations=1)
            component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
            for component_id in range(1, component_count):
                left, top, comp_width, comp_height, _area = [int(value) for value in stats[component_id]]
                component_mask = (labels == component_id).astype(np.uint8) * 255
                candidate = candidate_from_component(
                    zone_name=zone.name,
                    rect=(left, top, comp_width, comp_height),
                    component_mask=component_mask,
                    heat=heat,
                    edge_frequency=edge_frequency,
                    mean_edges=mean_edges,
                    scale=scale,
                    zone_offset=(zone_left, zone_top),
                    full_frame_size=frame_size,
                    frame_count=len(frames_with_times),
                    sample_times=sample_times,
                )
                if candidate is not None:
                    candidates.append(candidate)
                else:
                    candidates.extend(
                        extract_subcomponent_candidates(
                            zone_name=zone.name,
                            rect=(left, top, comp_width, comp_height),
                            component_mask=component_mask,
                            heat=heat,
                            edge_frequency=edge_frequency,
                            mean_edges=mean_edges,
                            scale=scale,
                            zone_offset=(zone_left, zone_top),
                            full_frame_size=frame_size,
                            frame_count=len(frames_with_times),
                            sample_times=sample_times,
                        )
                    )
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[:max_candidates]
    finally:
        capture.release()


def clamp_rect(rect: tuple[int, int, int, int], frame_size: tuple[int, int]) -> tuple[int, int, int, int]:
    frame_width, frame_height = frame_size
    left, top, right, bottom = rect
    return (
        max(0, min(left, frame_width - 1)),
        max(0, min(top, frame_height - 1)),
        max(left + 1, min(right, frame_width)),
        max(top + 1, min(bottom, frame_height)),
    )


def crop_rect(frame_bgr: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    height, width = frame_bgr.shape[:2]
    left, top, right, bottom = clamp_rect(rect, (width, height))
    return frame_bgr[top:bottom, left:right]


def normalize_gray(image_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.equalizeHist(gray)


def edge_image(gray: np.ndarray) -> np.ndarray:
    return cv2.Canny(gray, 35, 110)


def build_template_mask(reference_gray: np.ndarray) -> np.ndarray:
    background = cv2.GaussianBlur(reference_gray, (0, 0), sigmaX=7, sigmaY=7)
    prominence = cv2.absdiff(reference_gray, background)
    edges = edge_image(reference_gray)
    if int(np.count_nonzero(prominence)) == 0:
        prominence_mask = np.zeros(reference_gray.shape, dtype=np.uint8)
    else:
        threshold = max(8.0, float(np.percentile(prominence, 82)))
        prominence_mask = (prominence >= threshold).astype(np.uint8) * 255
    edge_mask = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.bitwise_or(prominence_mask, edge_mask)
    mask = remove_long_horizontal_lines(mask)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    return np.ones(reference_gray.shape, dtype=np.uint8) * 255 if int(np.count_nonzero(mask)) < 12 else mask


def _record_elapsed(timings: dict[str, float] | None, key: str, started: float) -> None:
    if timings is not None:
        timings[key] = timings.get(key, 0.0) + time.perf_counter() - started


def overlay_present_score_from_crop(
    reference: OverlayReference,
    crop: np.ndarray,
    timings: dict[str, float] | None = None,
    details: dict[str, float] | None = None,
) -> float:
    """Score an already-cropped BGR ROI with the released sensor calculation."""
    if crop.size == 0:
        if details is not None:
            details.update(gray_score=0.0, edge_score=0.0, score=0.0)
        return 0.0

    started = time.perf_counter()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _record_elapsed(timings, "cvt_color", started)
    started = time.perf_counter()
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _record_elapsed(timings, "blur", started)
    started = time.perf_counter()
    gray = cv2.equalizeHist(gray)
    _record_elapsed(timings, "equalize_hist", started)
    if gray.shape != reference.gray.shape:
        started = time.perf_counter()
        gray = cv2.resize(gray, (reference.gray.shape[1], reference.gray.shape[0]), interpolation=cv2.INTER_AREA)
        _record_elapsed(timings, "resize", started)
    started = time.perf_counter()
    edges = edge_image(gray)
    _record_elapsed(timings, "canny", started)
    try:
        started = time.perf_counter()
        edge_score = cv2.matchTemplate(edges, reference.edges, cv2.TM_CCORR_NORMED, mask=reference.edge_mask)
        _record_elapsed(timings, "edge_correlation", started)
        started = time.perf_counter()
        gray_score = cv2.matchTemplate(gray, reference.gray, cv2.TM_CCORR_NORMED, mask=reference.template_mask)
        _record_elapsed(timings, "gray_correlation", started)
    except cv2.error:
        if details is not None:
            details.update(gray_score=0.0, edge_score=0.0, score=0.0)
        return 0.0
    started = time.perf_counter()
    edge_value = float(cv2.minMaxLoc(edge_score)[1])
    gray_value = float(cv2.minMaxLoc(gray_score)[1])
    _record_elapsed(timings, "correlation_minmax", started)
    if not np.isfinite(edge_value):
        edge_value = 0.0
    if not np.isfinite(gray_value):
        gray_value = 0.0
    edge_value = max(0.0, min(1.0, edge_value))
    gray_value = max(0.0, min(1.0, gray_value))
    value = max(0.0, min(1.0, edge_value * 0.76 + gray_value * 0.24))
    if details is not None:
        details.update(gray_score=gray_value, edge_score=edge_value, score=value)
    return value


def overlay_present_score(reference: OverlayReference, frame_bgr: np.ndarray) -> float:
    return overlay_present_score_from_crop(reference, crop_rect(frame_bgr, reference.overlay.rect))
