from __future__ import annotations

import bisect
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path


SCHEMA_VERSION = "commercial-edge-refiner-v1"
PRESENT = "PRESENT"
ABSENT = "ABSENT"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LogoRun:
    start_frame: int
    end_frame: int
    state: str


@dataclass(frozen=True)
class TailExtension:
    commercial_index: int
    commercial_start_frame: int
    original_end_frame: int
    proposed_end_frame: int
    normal_logo_return_frame: int
    extension_frames: int
    extension_seconds: float
    absent_evidence_fraction: float
    reason: str = "STABLE_NORMAL_LOGO_RETURN"


def _normalized_state(value: object) -> str:
    return str(value) if value in (PRESENT, ABSENT) else UNKNOWN


def read_comskip_logo_runs(sidecar_path: Path) -> tuple[list[LogoRun], str | None, int]:
    """Stream the existing sidecar and compact its fixed-position Comskip states."""
    runs: list[LogoRun] = []
    reliability: str | None = None
    observations = 0
    active_start: int | None = None
    active_end: int | None = None
    active_state: str | None = None

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
            if row.get("record_type") != "observation" or row.get("comskip_frame") is None:
                continue

            frame = int(row["comskip_frame"])
            state = _normalized_state(row.get("comskip_local_state"))
            observations += 1
            if active_start is None:
                active_start = active_end = frame
                active_state = state
                continue
            if frame < int(active_end):
                raise RuntimeError("Comskip logo observations are not ordered by frame")
            if frame == active_end:
                if state != active_state:
                    active_state = UNKNOWN
                continue
            if frame == int(active_end) + 1 and state == active_state:
                active_end = frame
                continue

            runs.append(LogoRun(int(active_start), int(active_end), str(active_state)))
            if frame > int(active_end) + 1:
                runs.append(LogoRun(int(active_end) + 1, frame - 1, UNKNOWN))
            active_start = active_end = frame
            active_state = state

    if active_start is not None:
        runs.append(LogoRun(int(active_start), int(active_end), str(active_state)))
    return runs, reliability, observations


def parse_comskip_txt(path: Path) -> tuple[str, int, list[tuple[int, int]]]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if not lines or not lines[0].startswith("FILE PROCESSING COMPLETE "):
        raise RuntimeError(f"Cannot inspect incomplete Comskip TXT: {path}")
    fields = lines[0].split()
    total_frames = int(fields[3])
    intervals: list[tuple[int, int]] = []
    for line in lines[2:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            intervals.append((int(parts[0]), int(parts[1])))
    return lines[0], total_frames, intervals


def propose_tail_extensions(
    intervals: list[tuple[int, int]],
    runs: list[LogoRun],
    *,
    fps: float,
    total_frames: int,
    max_tail_seconds: float = 180.0,
    min_extension_seconds: float = 5.0,
    return_confirmation_seconds: float = 2.0,
    minimum_absent_fraction: float = 0.80,
) -> list[TailExtension]:
    if fps <= 0:
        raise ValueError("FPS must be positive")
    if max_tail_seconds <= 0 or min_extension_seconds < 0 or return_confirmation_seconds <= 0:
        raise ValueError("Commercial edge timing parameters are invalid")
    if not 0.0 <= minimum_absent_fraction <= 1.0:
        raise ValueError("minimum_absent_fraction must be between zero and one")
    if not intervals or not runs:
        return []

    run_ends = [run.end_frame for run in runs]
    max_tail_frames = max(1, int(round(max_tail_seconds * fps)))
    min_extension_frames = max(1, int(round(min_extension_seconds * fps)))
    confirmation_frames = max(1, int(round(return_confirmation_seconds * fps)))
    proposals: list[TailExtension] = []

    for commercial_index, (commercial_start, commercial_end) in enumerate(intervals):
        first_tail_frame = commercial_end + 1
        if first_tail_frame >= total_frames:
            continue
        run_index = bisect.bisect_left(run_ends, first_tail_frame)
        if run_index >= len(runs):
            continue
        first_run = runs[run_index]
        if not (first_run.start_frame <= first_tail_frame <= first_run.end_frame):
            continue
        if first_run.state != ABSENT:
            continue

        scan_limit = min(total_frames - 1, commercial_end + max_tail_frames)
        normal_logo_return: int | None = None
        absent_frames = 0
        inspected_frames = 0
        candidate_index = run_index
        while candidate_index < len(runs):
            run = runs[candidate_index]
            if run.start_frame > scan_limit:
                break
            segment_start = max(first_tail_frame, run.start_frame)
            segment_end = min(scan_limit, run.end_frame)
            if segment_end < segment_start:
                candidate_index += 1
                continue
            segment_frames = segment_end - segment_start + 1
            if run.state == PRESENT and segment_frames >= confirmation_frames:
                normal_logo_return = segment_start
                break
            inspected_frames += segment_frames
            if run.state == ABSENT:
                absent_frames += segment_frames
            candidate_index += 1

        if normal_logo_return is None:
            continue
        proposed_end = normal_logo_return - 1
        extension_frames = proposed_end - commercial_end
        if extension_frames < min_extension_frames:
            continue
        absent_fraction = absent_frames / max(1, inspected_frames)
        if absent_fraction < minimum_absent_fraction:
            continue
        proposals.append(
            TailExtension(
                commercial_index=commercial_index,
                commercial_start_frame=commercial_start,
                original_end_frame=commercial_end,
                proposed_end_frame=proposed_end,
                normal_logo_return_frame=normal_logo_return,
                extension_frames=extension_frames,
                extension_seconds=round(extension_frames / fps, 6),
                absent_evidence_fraction=round(absent_fraction, 6),
            )
        )
    return proposals


def analyze_commercial_edges(
    *,
    txt_path: Path,
    sidecar_path: Path,
    fps: float,
    max_tail_seconds: float = 180.0,
    min_extension_seconds: float = 5.0,
    return_confirmation_seconds: float = 2.0,
    minimum_absent_fraction: float = 0.80,
) -> dict:
    started = time.perf_counter()
    _header, total_frames, intervals = parse_comskip_txt(txt_path)
    runs, reliability, observations = read_comskip_logo_runs(sidecar_path)
    sensor_usable = reliability == "ACCEPTED_BY_EXISTING_GATE" and observations > 0
    proposals = (
        propose_tail_extensions(
            intervals,
            runs,
            fps=fps,
            total_frames=total_frames,
            max_tail_seconds=max_tail_seconds,
            min_extension_seconds=min_extension_seconds,
            return_confirmation_seconds=return_confirmation_seconds,
            minimum_absent_fraction=minimum_absent_fraction,
        )
        if sensor_usable
        else []
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ANALYZED" if sensor_usable else "SKIPPED_LOGO_SENSOR_UNAVAILABLE",
        "strategy": "fixed_position_normal_logo_return_after_existing_commercial",
        "video_decode_required": False,
        "logo_sensor_reliability": reliability,
        "logo_observations": observations,
        "compacted_logo_runs": len(runs),
        "commercial_count": len(intervals),
        "config": {
            "max_tail_seconds": max_tail_seconds,
            "min_extension_seconds": min_extension_seconds,
            "return_confirmation_seconds": return_confirmation_seconds,
            "minimum_absent_fraction": minimum_absent_fraction,
        },
        "proposals": [asdict(proposal) for proposal in proposals],
        "runtime_seconds": round(time.perf_counter() - started, 6),
    }


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def apply_commercial_edge_extensions(
    *,
    txt_path: Path,
    edl_path: Path,
    report: dict,
    fps: float,
) -> dict:
    header, _total_frames, existing = parse_comskip_txt(txt_path)
    replacements = {
        int(proposal["commercial_index"]): int(proposal["proposed_end_frame"])
        for proposal in report.get("proposals", [])
    }
    extended = [
        (start, max(end, replacements.get(index, end)))
        for index, (start, end) in enumerate(existing)
    ]
    merged = _merge_intervals(extended)

    pre_txt = txt_path.with_name(txt_path.stem + "-pre-edge-refiner.txt")
    pre_edl = edl_path.with_name(edl_path.stem + "-pre-edge-refiner.edl")
    shutil.copy2(txt_path, pre_txt)
    if edl_path.is_file():
        shutil.copy2(edl_path, pre_edl)

    txt_payload = header + "\n-------------------\n"
    txt_payload += "".join(f"{start}\t{end}\n" for start, end in merged)
    edl_payload = "".join(f"{start / fps:.3f}\t{end / fps:.3f}\t0\n" for start, end in merged)
    txt_temporary = txt_path.with_name(txt_path.name + ".edge-refiner.tmp")
    edl_temporary = edl_path.with_name(edl_path.name + ".edge-refiner.tmp")
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
        "extended_intervals": [list(interval) for interval in merged],
        "pre_refiner_txt": str(pre_txt),
        "pre_refiner_edl": str(pre_edl) if pre_edl.is_file() else None,
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
