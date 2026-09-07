"""Bounds for decoding frames, distinct from an exclusive cut/file endpoint."""
from __future__ import annotations

import math


def last_frame_seconds(total_frames: int, fps: float) -> float:
    if total_frames < 1 or not math.isfinite(fps) or fps <= 0:
        raise ValueError("Positive frame count and finite frame rate required")
    return (total_frames - 1) / fps


def sample_seconds_within_video(duration: float, total_frames: int, fps: float,
                                step: float) -> list[float]:
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(step) or step <= 0:
        raise ValueError("Positive finite duration and sampling step required")
    last = min(duration, last_frame_seconds(total_frames, fps))
    return [index * step for index in range(math.floor(last / step) + 1)]
