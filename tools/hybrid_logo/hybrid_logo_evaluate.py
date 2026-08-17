from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


FILMS = {
    "american_assassin": {
        "ads": [(37700, 51300), (86800, 95600), (126700, 136000), (167100, 177900)],
        "show": [(8000, 9500), (16100, 18000), (22800, 23800), (140700, 144800), (179300, 180200), (214740, 214745)],
    },
    "freelance": {
        "ads": [(49414, 56168), (90502, 98346), (170046, 176993)],
        "show": [],
    },
    "one_day_as_a_lion": {
        "ads": [(25458, 33804)],
        "show": [(1, 7198), (155184, 177244)],
    },
    "lion_king_2": {"ads": [], "show": []},
    "hateful_eight": {"ads": [], "show": []},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the fixed Phase-2C baseline/hybrid experiment.")
    parser.add_argument("--phase2c-root", type=Path, required=True)
    parser.add_argument("--phase2b-root", type=Path, required=True)
    return parser.parse_args()


def only(path: Path, pattern: str) -> Path:
    matches = list(path.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"Expected one {pattern} below {path}, found {len(matches)}")
    return matches[0]


def result_txt(path: Path) -> Path:
    matches = [item for item in path.glob("*.txt") if not item.name.endswith(".logo.txt")]
    if len(matches) != 1:
        raise ValueError(f"Expected one result txt below {path}, found {len(matches)}")
    return matches[0]


def intervals(path: Path) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r"\s*(\d+)\s+(-?\d+)\s*", line)
        if match:
            result.append((int(match.group(1)), int(match.group(2))))
    return result


def overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]) + 1)


def covered(region: tuple[int, int], predicted: list[tuple[int, int]]) -> int:
    return sum(overlap(region, interval) for interval in predicted)


def truth_metrics(truth: dict, predicted: list[tuple[int, int]]) -> dict:
    ad_total = sum(end - start + 1 for start, end in truth["ads"])
    ad_correct = sum(covered(region, predicted) for region in truth["ads"])
    show_total = sum(end - start + 1 for start, end in truth["show"])
    show_false = sum(covered(region, predicted) for region in truth["show"])
    return {
        "ground_truth_ad_frames": ad_total,
        "correct_ad_frames": ad_correct,
        "missed_ad_frames": ad_total - ad_correct,
        "ground_truth_show_frames": show_total,
        "false_positive_show_frames": show_false,
        "regions": [
            {
                "kind": kind,
                "start": start,
                "end": end,
                "frames": end - start + 1,
                "classified_commercial": covered((start, end), predicted),
            }
            for kind in ("ads", "show")
            for start, end in truth[kind]
        ],
    }


def load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def classification_at(frame: int, commercial: list[tuple[int, int]]) -> str:
    return "COMMERCIAL" if any(start <= frame <= end for start, end in commercial) else "SHOW"


def changed_ranges(
    baseline: list[tuple[int, int]], hybrid: list[tuple[int, int]], maximum_frame: int
) -> list[tuple[int, int, str, str]]:
    boundaries = {1, maximum_frame + 1}
    for start, end in baseline + hybrid:
        boundaries.add(max(1, start))
        boundaries.add(min(maximum_frame + 1, end + 1))
    ordered = sorted(boundaries)
    raw: list[tuple[int, int, str, str]] = []
    for start, after in zip(ordered, ordered[1:]):
        end = after - 1
        base_class = classification_at(start, baseline)
        hybrid_class = classification_at(start, hybrid)
        if base_class != hybrid_class:
            raw.append((start, end, base_class, hybrid_class))
    merged: list[tuple[int, int, str, str]] = []
    for item in raw:
        if merged and merged[-1][1] + 1 == item[0] and merged[-1][2:] == item[2:]:
            merged[-1] = (merged[-1][0], item[1], item[2], item[3])
        else:
            merged.append(item)
    return merged


def best_block(rows: list[dict], changed: tuple[int, int, str, str]) -> dict:
    region = changed[:2]
    return max(
        rows,
        key=lambda row: overlap(region, (int(row["frame_start"]), int(row["frame_end"]))),
    )


def length_rule(duration: float, minimum_show_seconds: float = 250.0) -> str:
    if duration > 2 * minimum_show_seconds:
        return "twice_excess_length"
    if duration > minimum_show_seconds:
        return "excess_length"
    return "none"


def changed_diagnostics(
    changes: list[tuple[int, int, str, str]], baseline_rows: list[dict], hybrid_rows: list[dict]
) -> list[dict]:
    result = []
    atomic_changes: list[tuple[int, int, str, str]] = []
    for start, end, baseline_class, hybrid_class in changes:
        boundaries = {start, end + 1}
        for row in baseline_rows + hybrid_rows:
            block_start = int(row["frame_start"])
            block_after = int(row["frame_end"]) + 1
            if block_start <= end and block_after > start:
                boundaries.add(max(start, block_start))
                boundaries.add(min(end + 1, block_after))
        ordered = sorted(boundaries)
        atomic_changes.extend(
            (part_start, part_after - 1, baseline_class, hybrid_class)
            for part_start, part_after in zip(ordered, ordered[1:])
            if part_start < part_after
        )

    for start, end, baseline_class, hybrid_class in atomic_changes:
        base = best_block(baseline_rows, (start, end, baseline_class, hybrid_class))
        hybrid = best_block(hybrid_rows, (start, end, baseline_class, hybrid_class))
        result.append(
            {
                "frame_start": start,
                "frame_end": end,
                "pts_start": round(start / 25.0, 6),
                "pts_end": round(end / 25.0, 6),
                "length_seconds": round((end - start + 1) / 25.0, 6),
                "baseline_block": int(base["block"]),
                "baseline_block_start": int(base["frame_start"]),
                "baseline_block_end": int(base["frame_end"]),
                "hybrid_block": int(hybrid["block"]),
                "hybrid_block_start": int(hybrid["frame_start"]),
                "hybrid_block_end": int(hybrid["frame_end"]),
                "comskip_legacy_logo_fraction": float(hybrid["comskip_legacy_logo_fraction"]),
                "comskip_logo_fraction": float(hybrid["comskip_sidecar_present_fraction"]),
                "logofinder_logo_fraction": float(hybrid["logofinder_present_fraction"]),
                "fusion_present_fraction": float(hybrid["fusion_present_fraction"]),
                "fusion_absent_fraction": float(hybrid["fusion_absent_fraction"]),
                "fusion_conflict_fraction": float(hybrid["fusion_conflict_fraction"]),
                "fusion_unknown_fraction": float(hybrid["fusion_unknown_fraction"]),
                "baseline_score": float(base["normal_score"]),
                "hybrid_score": float(hybrid["hybrid_score"]),
                "baseline_logo_modifier": float(base["normal_logo_modifier"]),
                "hybrid_logo_modifier": float(hybrid["hybrid_logo_modifier"]),
                "baseline_block_excessive_length": length_rule(
                    float(base["time_end"]) - float(base["time_start"])
                ),
                "hybrid_block_baseline_length_rule": hybrid["excessive_length_would_apply"],
                "baseline_class": baseline_class,
                "hybrid_class": hybrid_class,
            }
        )
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_seconds(log: Path) -> float:
    text = log.read_text(encoding="utf-8", errors="replace")
    decoded = re.findall(r"frames decoded in ([0-9.]+) seconds", text)
    if decoded:
        return float(decoded[-1])
    stamps = re.findall(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Z][a-z]{2} \d{1,2} \d{2}:\d{2}:\d{2} \d{4}", text)
    if len(stamps) >= 2:
        start = datetime.strptime(stamps[0], "%a %b %d %H:%M:%S %Y")
        end = datetime.strptime(stamps[-1], "%a %b %d %H:%M:%S %Y")
        return (end - start).total_seconds()
    raise ValueError(f"No runtime in {log}")


def evaluate(args: argparse.Namespace) -> dict:
    report: dict = {"films": {}}
    changed_csv_rows: list[dict] = []
    for name, truth in FILMS.items():
        film_root = args.phase2c_root / name
        baseline_dir = film_root / "baseline"
        hybrid_dir = film_root / "hybrid"
        previous_dir = args.phase2b_root / name
        baseline_intervals = intervals(result_txt(baseline_dir))
        hybrid_intervals = intervals(result_txt(hybrid_dir))
        baseline_rows = load_csv(only(previous_dir, "*.hybrid-logo-shadow.csv"))
        hybrid_rows = load_csv(only(hybrid_dir, "*.hybrid-logo-experimental.csv"))
        metadata = json.loads(
            (film_root / "logofinder_framewise" / "hybrid_logo_metadata.json").read_text(encoding="utf-8")
        )
        fusion = json.loads((film_root / "hybrid-logo-framewise-v1-summary.json").read_text(encoding="utf-8"))
        maximum_frame = int(metadata["video_metadata"]["total_frames"]) - 1
        changes = changed_ranges(baseline_intervals, hybrid_intervals, maximum_frame)
        diagnostics = changed_diagnostics(changes, baseline_rows, hybrid_rows)
        for row in diagnostics:
            changed_csv_rows.append({"film": name, **row})

        invariance = {}
        for suffix in ("result.txt", "*.edl", "*.logo.txt", "*.logo-raw.csv"):
            current = result_txt(baseline_dir) if suffix == "result.txt" else only(baseline_dir, suffix)
            previous = result_txt(previous_dir) if suffix == "result.txt" else only(previous_dir, suffix)
            invariance[suffix] = {
                "current_sha256": sha256(current),
                "previous_sha256": sha256(previous),
                "identical": sha256(current) == sha256(previous),
            }
        report["films"][name] = {
            "baseline_intervals": baseline_intervals,
            "hybrid_intervals": hybrid_intervals,
            "baseline_truth": truth_metrics(truth, baseline_intervals),
            "hybrid_truth": truth_metrics(truth, hybrid_intervals),
            "changed_ranges": diagnostics,
            "baseline_invariance": invariance,
            "performance_seconds": {
                **metadata["performance_seconds"],
                "fusion": fusion["performance_seconds"]["total"],
                "baseline_comskip": runtime_seconds(only(baseline_dir, "*.log")),
                "hybrid_comskip": runtime_seconds(only(hybrid_dir, "*.log")),
                "hybrid_total": metadata["performance_seconds"]["total"]
                + fusion["performance_seconds"]["total"]
                + runtime_seconds(only(hybrid_dir, "*.log")),
            },
            "logofinder_frames_checked": metadata["timeline"]["output_points"],
            "fusion_counts": fusion["coarse_fusion_counts"],
            "fusion_state_changes": len(fusion["state_changes"]),
        }

    output = args.phase2c_root / "phase2c_evaluation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_path = args.phase2c_root / "phase2c_changed_ranges.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(changed_csv_rows[0]) if changed_csv_rows else ["film"])
        writer.writeheader()
        writer.writerows(changed_csv_rows)
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate(parse_args()), ensure_ascii=False, indent=2, sort_keys=True))
