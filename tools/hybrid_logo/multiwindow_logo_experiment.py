from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from hybrid_logo_analysis import run as run_internal_logo_analysis
from hybrid_logo_fusion import run as run_hybrid_logo_fusion


LEARNING_GUARD_SECONDS = 6 * 60
WINDOW_COUNT = 5
DEFAULT_WINDOW_SECONDS = 120.0


@dataclass(frozen=True)
class LearningWindow:
    index: int
    start_seconds: float
    end_seconds: float


@dataclass
class MaskCandidate:
    window: LearningWindow
    path: Path
    bbox: tuple[int, int, int, int]
    picture_size: tuple[int, int]
    horizontal_edges: set[tuple[int, int]]
    vertical_edges: set[tuple[int, int]]
    validation_quality: float
    validation_present_fraction: float
    validation_samples: int
    support_count: int = 0
    recurrence_score: float = 0.0
    selection_score: float = 0.0


FILMS = (
    ("american_assassin", Path(r"C:\Users\XMG Studio\Downloads\2026-08-07_22-25_American-Assassin_pro-7_hq.mp4")),
    ("freelance", Path(r"C:\Users\XMG Studio\Downloads\2026-08-07_20-15_Freelance_pro-7_hq.mp4")),
    ("one_day_as_a_lion", Path(r"C:\Users\XMG Studio\Downloads\2026-08-08_00-35_One-Day-As-A-Lion_pro-7_hq.mp4")),
    ("lion_king_2", Path(r"C:\Users\XMG Studio\Downloads\2026-08-07_18-55_Der-Koenig-Der-Loewen-2-Simbas-Koenigreich_disney-channel_hq.mp4")),
    ("hateful_eight", Path(r"C:\Users\XMG Studio\Downloads\2026-08-07_23-22_The-Hateful-Eight_rtlzwei_hq.mp4")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the five-film final multiwindow logo verification.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sight-root", type=Path, required=True)
    parser.add_argument("--comskip", type=Path, required=True)
    parser.add_argument("--ini", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    parser.add_argument("--ffprobe", type=Path, default=Path("ffprobe"))
    parser.add_argument("--window-seconds", type=float, default=DEFAULT_WINDOW_SECONDS)
    parser.add_argument("--resume-incomplete", action="store_true")
    parser.add_argument("--film", choices=[key for key, _video in FILMS], action="append")
    return parser.parse_args()


def run_command(
    command: list[str],
    *,
    log_path: Path,
    cwd: Path | None = None,
    accepted_exit_codes: tuple[int, ...] = (0,),
) -> float:
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        log.write(json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        environment = os.environ.copy()
        mingw_bin = Path(r"C:\msys64\mingw64\bin")
        if mingw_bin.is_dir():
            environment["PATH"] = str(mingw_bin) + os.pathsep + environment.get("PATH", "")
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    if completed.returncode not in accepted_exit_codes:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}; see {log_path}")
    return elapsed


def probe_video(ffprobe: Path, video: Path) -> dict:
    command = [
        str(ffprobe), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,nb_frames,width,height:format=duration",
        "-of", "json", str(video),
    ]
    payload = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))
    stream = payload["streams"][0]
    numerator, denominator = stream["avg_frame_rate"].split("/", 1)
    fps = float(numerator) / float(denominator)
    duration = float(payload["format"]["duration"])
    total_frames = int(stream.get("nb_frames") or round(duration * fps))
    return {
        "duration_seconds": duration,
        "fps": fps,
        "total_frames": total_frames,
        "width": int(stream["width"]),
        "height": int(stream["height"]),
    }


def learning_windows(duration: float, window_seconds: float = DEFAULT_WINDOW_SECONDS) -> list[LearningWindow]:
    start = float(LEARNING_GUARD_SECONDS)
    end = duration - LEARNING_GUARD_SECONDS
    usable = end - start
    if usable <= 0:
        raise ValueError("Video is too short for two hard six-minute learning guards")
    stratum = usable / WINDOW_COUNT
    actual_window = min(window_seconds, stratum * 0.8)
    if actual_window <= 0:
        raise ValueError("No positive multiwindow learning duration")
    windows = []
    for index in range(WINDOW_COUNT):
        center = start + stratum * (index + 0.5)
        left = center - actual_window / 2
        right = center + actual_window / 2
        windows.append(LearningWindow(index + 1, left, right))
    if any(left.end_seconds > right.start_seconds for left, right in zip(windows, windows[1:])):
        raise AssertionError("Learning windows overlap")
    return windows


def parse_mask(path: Path, window: LearningWindow, quality: tuple[float, float, int]) -> MaskCandidate:
    raw = path.read_bytes().decode("latin-1")
    values: dict[str, int] = {}
    for key in ("logoMinX", "logoMaxX", "logoMinY", "logoMaxY", "picWidth", "picHeight"):
        for line in raw.splitlines():
            if line.startswith(key + "="):
                values[key] = int(line.split("=", 1)[1])
                break
    missing = [key for key in ("logoMinX", "logoMaxX", "logoMinY", "logoMaxY", "picWidth", "picHeight") if key not in values]
    if missing:
        raise ValueError(f"Mask {path} is missing {', '.join(missing)}")
    marker = raw.find("\x82")
    if marker < 0:
        raise ValueError(f"Mask {path} has no combined H/V mask")
    lines = raw[marker + 1 :].lstrip("\r\n").splitlines()
    min_x, max_x = values["logoMinX"], values["logoMaxX"]
    min_y, max_y = values["logoMinY"], values["logoMaxY"]
    mask_width = max_x - min_x + 1
    mask_height = max_y - min_y + 1
    if len(lines) < mask_height:
        raise ValueError(f"Mask {path} is truncated")
    horizontal: set[tuple[int, int]] = set()
    vertical: set[tuple[int, int]] = set()
    for offset_y, line in enumerate(lines[:mask_height]):
        padded = line.ljust(mask_width)
        for offset_x, char in enumerate(padded[:mask_width]):
            point = (min_x + offset_x, min_y + offset_y)
            if char in "|+":
                horizontal.add(point)
            if char in "-+":
                vertical.add(point)
    return MaskCandidate(
        window=window,
        path=path,
        bbox=(min_x, min_y, max_x, max_y),
        picture_size=(values["picWidth"], values["picHeight"]),
        horizontal_edges=horizontal,
        vertical_edges=vertical,
        validation_quality=quality[0],
        validation_present_fraction=quality[1],
        validation_samples=quality[2],
    )


def candidate_quality(raw_csv: Path) -> tuple[float, float, int]:
    good_edges: list[float] = []
    present = 0
    with raw_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            edge = float(row["comskip_good_edge"])
            if edge <= 0:
                continue
            good_edges.append(edge)
            present += int(row["comskip_present"])
    if not good_edges:
        return 0.0, 0.0, 0
    mean_edge = sum(good_edges) / len(good_edges)
    present_fraction = present / len(good_edges)
    return min(1.0, mean_edge), present_fraction, len(good_edges)


def bbox_iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    ix = max(0, min(left[2], right[2]) - max(left[0], right[0]) + 1)
    iy = max(0, min(left[3], right[3]) - max(left[1], right[1]) + 1)
    intersection = ix * iy
    left_area = (left[2] - left[0] + 1) * (left[3] - left[1] + 1)
    right_area = (right[2] - right[0] + 1) * (right[3] - right[1] + 1)
    return intersection / max(1, left_area + right_area - intersection)


def dilated_overlap(left: set[tuple[int, int]], right: set[tuple[int, int]], radius: int = 2) -> float:
    if not left or not right:
        return 0.0
    def covered(source: set[tuple[int, int]], target: set[tuple[int, int]]) -> int:
        return sum(
            any((x + dx, y + dy) in target for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1))
            for x, y in source
        )
    precision = covered(left, right) / len(left)
    recall = covered(right, left) / len(right)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def mask_similarity(left: MaskCandidate, right: MaskCandidate) -> dict[str, float | bool]:
    iou = bbox_iou(left.bbox, right.bbox)
    horizontal = dilated_overlap(left.horizontal_edges, right.horizontal_edges)
    vertical = dilated_overlap(left.vertical_edges, right.vertical_edges)
    lc = ((left.bbox[0] + left.bbox[2]) / 2, (left.bbox[1] + left.bbox[3]) / 2)
    rc = ((right.bbox[0] + right.bbox[2]) / 2, (right.bbox[1] + right.bbox[3]) / 2)
    center_distance = math.dist(lc, rc)
    position_match = center_distance <= 24 and iou >= 0.20
    edge_match = (horizontal + vertical) / 2 >= 0.12
    score = iou * 0.35 + horizontal * 0.325 + vertical * 0.325
    return {
        "bbox_iou": iou,
        "horizontal_similarity": horizontal,
        "vertical_similarity": vertical,
        "center_distance": center_distance,
        "score": score,
        "recurring_match": position_match and edge_match,
    }


def select_recurring_candidate(candidates: list[MaskCandidate]) -> tuple[MaskCandidate | None, list[dict]]:
    comparisons: list[dict] = []
    adjacency = {index: set() for index in range(len(candidates))}
    pair_scores: dict[tuple[int, int], float] = {}
    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            metrics = mask_similarity(left, right)
            comparisons.append({
                "left_window": left.window.index,
                "right_window": right.window.index,
                **metrics,
            })
            pair_scores[(left_index, right_index)] = float(metrics["score"])
            if metrics["recurring_match"]:
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)
    clusters: list[set[int]] = []
    unseen = set(adjacency)
    while unseen:
        seed = unseen.pop()
        cluster = {seed}
        frontier = [seed]
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency[current]:
                if neighbor not in cluster:
                    cluster.add(neighbor)
                    unseen.discard(neighbor)
                    frontier.append(neighbor)
        clusters.append(cluster)
    recurring = [cluster for cluster in clusters if len(cluster) >= 2]
    if not recurring:
        return None, comparisons
    best_cluster = max(
        recurring,
        key=lambda cluster: (
            len(cluster),
            sum(pair_scores.get(tuple(sorted((a, b))), 0.0) for a in cluster for b in cluster if a < b),
        ),
    )
    for index in best_cluster:
        peers = [pair_scores[tuple(sorted((index, peer)))] for peer in best_cluster if peer != index]
        candidate = candidates[index]
        candidate.support_count = len(best_cluster)
        candidate.recurrence_score = sum(peers) / len(peers)
        candidate.selection_score = candidate.recurrence_score * 0.8 + candidate.validation_quality * 0.2
    return max((candidates[index] for index in best_cluster), key=lambda item: item.selection_score), comparisons


def comskip_command(
    args: argparse.Namespace,
    video: Path,
    output: Path,
    output_name: str,
    *,
    logo: Path | None = None,
    sidecar: Path | None = None,
    raw: bool = False,
    final: bool = False,
) -> list[str]:
    command = [
        str(args.comskip), "--ini", str(args.ini), "--output", str(output),
        "--output-filename", output_name,
    ]
    if logo is not None:
        command.extend(["--logo", str(logo)])
    if raw:
        command.append("--logo-raw")
    if sidecar is not None:
        command.extend(["--hybrid-logo-sidecar", str(sidecar)])
    command.append(str(video))
    return command


def compact_state(value: str) -> str:
    return {"PRESENT": "P", "ABSENT": "A", "CONFLICT": "C", "UNKNOWN": "U"}.get(value, "U")


def write_logo_stage(sidecar: Path, txt_path: Path, csv_path: Path, selected: MaskCandidate, fps: float) -> list[list[int]]:
    intervals: list[list[int]] = []
    interval_start: int | None = None
    last_frame = 0
    with sidecar.open("r", encoding="utf-8") as source, csv_path.open("w", encoding="utf-8", newline="") as csv_handle:
        writer = csv.writer(csv_handle, lineterminator="\n")
        writer.writerow([
            "frame", "pts_seconds", "comskip_state", "currentGoodEdge", "logofinder_state",
            "logofinder_score", "fusion_state", "selected_comskip_learning_mask",
            "comskip_global_reliability", "comskip_logo_percentage", "logofinder_global_reliability",
        ])
        for line in source:
            row = json.loads(line)
            if row.get("record_type") != "observation":
                continue
            aligned_comskip_frame = row.get("comskip_frame")
            frame = (
                int(aligned_comskip_frame)
                if aligned_comskip_frame is not None
                else int(row["logofinder_frame"]) + 1
            )
            last_frame = frame
            fusion = str(row["fusion_state"])
            if fusion == "ABSENT" and interval_start is None:
                interval_start = frame
            elif fusion != "ABSENT" and interval_start is not None:
                intervals.append([interval_start, frame - 1])
                interval_start = None
            writer.writerow([
                frame,
                row["time_seconds"],
                compact_state(str(row["comskip_local_state"])) if aligned_comskip_frame is not None else "U",
                row["comskip_local_confidence"] if aligned_comskip_frame is not None else "",
                compact_state(str(row["logofinder_stabilized_state"])),
                row["logofinder_raw_score"],
                compact_state(fusion),
                selected.path.name,
                row["comskip_global_reliability"],
                row["comskip_global_logo_percentage"],
                row["logofinder_global_reliability"],
            ])
    if interval_start is not None:
        intervals.append([interval_start, last_frame])
    with txt_path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write(f"FILE PROCESSING COMPLETE {last_frame} FRAMES AT  {int(round(fps * 100))}\n")
        handle.write("-------------------\n")
        for start, end in intervals:
            handle.write(f"{start}\t{end}\n")
    return intervals


def parse_comskip_intervals(path: Path) -> list[list[int]]:
    intervals: list[list[int]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            intervals.append([int(parts[0]), int(parts[1])])
    return intervals


def run_film(args: argparse.Namespace, key: str, video: Path) -> dict:
    film_started = time.perf_counter()
    exit_trace = getattr(args, "exit_trace", lambda _stage, **_details: None)
    film_root = args.output_root / key
    film_root.mkdir(parents=True, exist_ok=args.resume_incomplete)
    metadata = probe_video(args.ffprobe, video)
    windows = learning_windows(metadata["duration_seconds"], args.window_seconds)
    candidates: list[MaskCandidate] = []
    window_records: list[dict] = []

    def process_learning_window(window: LearningWindow) -> tuple[dict, MaskCandidate | None, float]:
        window_root = film_root / "learning_windows" / f"window_{window.index}"
        window_root.mkdir(parents=True, exist_ok=args.resume_incomplete)
        clip = window_root / f"window_{window.index}.mp4"
        extract_command = [
            str(args.ffmpeg), "-hide_banner", "-loglevel", "warning", "-y",
            "-ss", f"{window.start_seconds:.6f}", "-i", str(video),
            "-t", f"{window.end_seconds - window.start_seconds:.6f}",
            "-map", "0:v:0", "-an", "-sn", "-c:v", "copy", "-avoid_negative_ts", "make_zero", str(clip),
        ]
        extract_seconds = 0.0 if clip.is_file() else run_command(extract_command, log_path=window_root / "ffmpeg.log")
        mask_path = window_root / f"window_{window.index}.logo.txt"
        raw_path = window_root / f"window_{window.index}.logo-raw.csv"
        if args.resume_incomplete and mask_path.is_file() and raw_path.is_file():
            scan_seconds = 0.0
        else:
            scan_seconds = run_command(
                comskip_command(args, clip, window_root, f"window_{window.index}", raw=True),
                log_path=window_root / "comskip-command.log",
                accepted_exit_codes=(0, 1),
            )
        record = {"window": asdict(window), "mask_learned": mask_path.is_file(), "runtime_seconds": extract_seconds + scan_seconds}
        candidate = None
        if mask_path.is_file() and raw_path.is_file():
            quality = candidate_quality(raw_path)
            candidate = parse_mask(mask_path, window, quality)
            record.update({
                "bbox": candidate.bbox,
                "horizontal_edge_count": len(candidate.horizontal_edges),
                "vertical_edge_count": len(candidate.vertical_edges),
                "validation_quality": candidate.validation_quality,
                "validation_present_fraction": candidate.validation_present_fraction,
                "validation_samples": candidate.validation_samples,
            })
        return record, candidate, extract_seconds + scan_seconds

    candidate_started = time.perf_counter()
    exit_trace("LEARNING_EXECUTOR_START", worker_count=len(windows))
    with ThreadPoolExecutor(max_workers=len(windows), thread_name_prefix="comskip-learning") as executor:
        processed_windows = list(executor.map(process_learning_window, windows))
    exit_trace("LEARNING_EXECUTOR_SHUTDOWN_END")
    candidate_seconds = time.perf_counter() - candidate_started
    for record, candidate, _seconds in processed_windows:
        window_records.append(record)
        if candidate is not None:
            candidates.append(candidate)
    selected, comparisons = select_recurring_candidate(candidates)
    if selected is None:
        diagnostic = {"status": "UNCERTAIN_NO_RECURRING_MASK", "windows": window_records, "comparisons": comparisons}
        (film_root / "multiwindow_diagnostic.json").write_text(json.dumps(diagnostic, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError(f"{key}: no recurring Comskip mask; marked uncertain and no random mask was forced")
    selected_path = film_root / "selected-comskip-logo.txt"
    shutil.copy2(selected.path, selected_path)

    base = video.stem
    sensor_root = film_root / "comskip_sensor"
    sensor_root.mkdir(exist_ok=args.resume_incomplete)
    raw_path = sensor_root / f"{base}.logo-raw.csv"
    sensor_txt = sensor_root / f"{base}.txt"
    if args.resume_incomplete and raw_path.is_file() and sensor_txt.is_file():
        sensor_seconds = 0.0
    else:
        sensor_seconds = run_command(
            comskip_command(args, video, sensor_root, base, logo=selected_path, raw=True),
            log_path=sensor_root / "comskip-command.log",
            accepted_exit_codes=(0, 1),
        )

    internal_sensor_root = film_root / "internal_logo_sensor"
    logofinder_timeline = internal_sensor_root / "hybrid_logo_timeline.jsonl"
    logofinder_metadata = internal_sensor_root / "hybrid_logo_metadata.json"
    if args.resume_incomplete and logofinder_timeline.is_file() and logofinder_metadata.is_file():
        logofinder_seconds = 0.0
    else:
        analysis_started = time.perf_counter()
        exit_trace("INTERNAL_LOGO_SENSOR_START")
        run_internal_logo_analysis(argparse.Namespace(
            video=video,
            output_dir=internal_sensor_root,
            comskip_raw=raw_path,
            ffmpeg=args.ffmpeg,
            sample_seconds=1.0,
            heatmap_samples=48,
            reference_samples=24,
            learning_start_seconds=float(LEARNING_GUARD_SECONDS),
            learning_end_seconds=metadata["duration_seconds"] - LEARNING_GUARD_SECONDS,
            present_threshold=0.42,
            sharp_delta=0.12,
            refine_subdivisions=5,
            every_frame=True,
            exit_trace=exit_trace,
        ))
        logofinder_seconds = time.perf_counter() - analysis_started
        exit_trace("INTERNAL_LOGO_SENSOR_END", duration_seconds=logofinder_seconds)

    sidecar = film_root / "hybrid-logo-multiwindow-v1.jsonl"
    if args.resume_incomplete and sidecar.is_file():
        fusion_seconds = 0.0
    else:
        fusion_started = time.perf_counter()
        exit_trace("FUSION_START")
        run_hybrid_logo_fusion(argparse.Namespace(
            timeline=logofinder_timeline,
            metadata=logofinder_metadata,
            comskip_raw=raw_path,
            output=sidecar,
            absent_threshold=0.38,
            present_threshold=0.46,
            boundary_threshold=0.42,
            median_window=3,
            persistence_samples=2,
            frame_persistence=2,
            max_alignment_seconds=0.10,
        ))
        fusion_seconds = time.perf_counter() - fusion_started
        exit_trace("FUSION_END", duration_seconds=fusion_seconds)

    logo_stage_txt = film_root / f"{base}.logo-stage.txt"
    logo_stage_csv = film_root / f"{base}.logo-stage.csv"
    logo_intervals = write_logo_stage(sidecar, logo_stage_txt, logo_stage_csv, selected, metadata["fps"])

    final_root = film_root / "final"
    final_root.mkdir(exist_ok=args.resume_incomplete)
    exit_trace("FINAL_COMSKIP_START")
    final_seconds = run_command(
        comskip_command(args, video, final_root, base, logo=selected_path, sidecar=sidecar, final=True),
        log_path=final_root / "comskip-command.log",
        accepted_exit_codes=(0, 1),
    )
    exit_trace("FINAL_COMSKIP_END", duration_seconds=final_seconds)
    generated_final = final_root / f"{base}.txt"
    final_stage_txt = film_root / f"{base}.final-stage.txt"
    shutil.copy2(generated_final, final_stage_txt)
    final_intervals = parse_comskip_intervals(final_stage_txt)
    exit_trace("FINAL_STAGE_VALIDATED", intervals=final_intervals)

    sight_logo = args.sight_root / f"{base}_LOGO_STAGE.txt"
    sight_final = args.sight_root / f"{base}_FINAL_STAGE.txt"
    shutil.copy2(logo_stage_txt, sight_logo)
    shutil.copy2(final_stage_txt, sight_final)

    sensor_rows = 0
    sensor_present = 0
    sensor_logo_percentage = 0.0
    sensor_global_enabled = False
    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            sensor_rows += 1
            sensor_present += int(row["comskip_present"])
            sensor_logo_percentage = float(row["global_logo_percentage"])
            sensor_global_enabled = bool(int(row["global_logo_enabled"]))
    legacy_would_disable = sensor_logo_percentage < 0.15 - 0.05 or sensor_logo_percentage > 0.85
    result = {
        "film": key,
        "video": str(video),
        "video_metadata": metadata,
        "learning_guard_start_seconds": LEARNING_GUARD_SECONDS,
        "learning_guard_end_seconds": metadata["duration_seconds"] - LEARNING_GUARD_SECONDS,
        "windows": window_records,
        "candidate_comparisons": comparisons,
        "selected_mask": {
            "source_window": selected.window.index,
            "path": str(selected_path),
            "bbox": selected.bbox,
            "horizontal_edge_count": len(selected.horizontal_edges),
            "vertical_edge_count": len(selected.vertical_edges),
            "support_count": selected.support_count,
            "recurrence_score": selected.recurrence_score,
            "validation_quality": selected.validation_quality,
            "selection_score": selected.selection_score,
        },
        "logofinder_learning_range_seconds": [LEARNING_GUARD_SECONDS, metadata["duration_seconds"] - LEARNING_GUARD_SECONDS],
        "comskip_logo_percentage": sensor_logo_percentage,
        "comskip_global_logo_enabled": sensor_global_enabled,
        "legacy_comskip_would_disable_logo": legacy_would_disable,
        "logo_stage_intervals": logo_intervals,
        "final_stage_intervals": final_intervals,
        "other_detector_change": {
            "added": [interval for interval in final_intervals if interval not in logo_intervals],
            "removed": [interval for interval in logo_intervals if interval not in final_intervals],
            "interval_lists_identical": logo_intervals == final_intervals,
        },
        "runtime_seconds": {
            "candidate_learning": candidate_seconds,
            "comskip_sensor": sensor_seconds,
            "logofinder": logofinder_seconds,
            "fusion": fusion_seconds,
            "final_comskip": final_seconds,
            "total": time.perf_counter() - film_started,
        },
        "outputs": {
            "logo_stage_txt": str(logo_stage_txt),
            "logo_stage_csv": str(logo_stage_csv),
            "final_stage_txt": str(final_stage_txt),
            "sight_logo_txt": str(sight_logo),
            "sight_final_txt": str(sight_final),
        },
    }
    (film_root / "multiwindow_diagnostic.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    exit_trace("RUN_FILM_OUTPUT_FILES_CLOSED")
    exit_trace("RUN_FILM_RETURN_PREPARE")
    return result


def main() -> int:
    args = parse_args()
    if args.output_root.exists():
        manifest = args.output_root / "multiwindow_logo_manifest.json"
        if not args.resume_incomplete or manifest.exists():
            print(f"Refusing to overwrite existing experiment root: {args.output_root}", file=sys.stderr)
            return 2
    for required in (args.comskip, args.ini):
        if not required.is_file():
            print(f"Required file not found: {required}", file=sys.stderr)
            return 2
    selected_films = [item for item in FILMS if not args.film or item[0] in args.film]
    missing = [str(video) for _key, video in selected_films if not video.is_file()]
    if missing:
        print("Missing reference videos: " + ", ".join(missing), file=sys.stderr)
        return 2
    args.output_root.mkdir(parents=True, exist_ok=args.resume_incomplete)
    args.sight_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results = []
    try:
        for key, video in selected_films:
            print(f"multiwindow-logo: starting {key}", flush=True)
            results.append(run_film(args, key, video))
    except Exception as exc:
        print(f"multiwindow-logo: {exc}", file=sys.stderr)
        return 1
    manifest = {
        "schema_version": "multiwindow-logo-experiment-v1",
        "learning_guard_seconds": LEARNING_GUARD_SECONDS,
        "window_count": WINDOW_COUNT,
        "final_logo_mode": "automatic_with_selected_mask_and_internal_sidecar",
        "runtime_seconds": time.perf_counter() - started,
        "films": results,
    }
    (args.output_root / "multiwindow_logo_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
