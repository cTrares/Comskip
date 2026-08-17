from __future__ import annotations

import argparse
import bisect
import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path


SCHEMA_VERSION = "hybrid-logo-shadow-v1"
PRESENT = "PRESENT"
ABSENT = "ABSENT"
CONFLICT = "CONFLICT"
UNKNOWN = "UNKNOWN"
NEUTRAL = "NEUTRAL"

BLOCK_LINE = re.compile(
    r"^\s*(?P<block>\d+):\S\S\s+"
    r"\d+\s+\d+\s+\d+\s+"
    r"(?P<frame_start>\d+)\s+(?P<frame_end>\d+)\s+"
    r"(?P<time_start>[0-9.]+)s\s+(?P<time_end>[0-9.]+)s\s+"
    r"(?P<length>[0-9.]+)s\s+(?P<score>[0-9.]+)"
)
THRESHOLD_LINE = re.compile(r"Threshold used -\s*([0-9.]+)")


@dataclass(frozen=True)
class NormalBlock:
    block: int
    frame_start: int
    frame_end: int
    time_start: float
    time_end: float
    length: float
    normal_score: float


@dataclass(frozen=True)
class TimelinePoint:
    time_seconds: float
    fusion_state: str
    comskip_state: str


@dataclass(frozen=True)
class Fractions:
    present: float
    absent: float
    conflict: float
    unknown: float
    covered_seconds: float
    block_seconds: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute a non-invasive hybrid-logo shadow score for final Comskip blocks."
    )
    parser.add_argument("--comskip-log", required=True, type=Path)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Shadow block CSV")
    parser.add_argument("--summary", type=Path, help="Summary JSON (defaults next to CSV)")
    parser.add_argument("--logo-percentage-threshold", type=float, default=0.25)
    parser.add_argument("--logo-present-modifier", type=float, default=0.01)
    parser.add_argument("--punish-no-logo", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def parse_comskip_log(path: Path) -> tuple[float, list[NormalBlock]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    markers = [match.start() for match in re.finditer(r"^Block list after weighing\s*$", text, re.MULTILINE)]
    if not markers:
        raise ValueError(f"No final block table found in {path}")
    section = text[markers[-1] :]
    thresholds = THRESHOLD_LINE.findall(text[: markers[-1]])
    if not thresholds:
        raise ValueError(f"No score threshold found in {path}")
    blocks: list[NormalBlock] = []
    for line in section.splitlines():
        match = BLOCK_LINE.match(line)
        if match:
            values = match.groupdict()
            blocks.append(
                NormalBlock(
                    block=int(values["block"]),
                    frame_start=int(values["frame_start"]),
                    frame_end=int(values["frame_end"]),
                    time_start=float(values["time_start"]),
                    time_end=float(values["time_end"]),
                    length=float(values["length"]),
                    normal_score=float(values["score"]),
                )
            )
        elif blocks:
            break
    if not blocks:
        raise ValueError(f"Final block table in {path} contains no blocks")
    return float(thresholds[-1]), blocks


def load_sidecar(path: Path) -> tuple[dict, list[TimelinePoint]]:
    points: list[TimelinePoint] = []
    with path.open("r", encoding="utf-8") as handle:
        metadata = json.loads(next(handle))
        if metadata.get("schema_version") != "hybrid-logo-v1":
            raise ValueError(f"Unsupported sidecar schema in {path}")
        for line in handle:
            row = json.loads(line)
            points.append(
                TimelinePoint(
                    time_seconds=float(row["time_seconds"]),
                    fusion_state=str(row["fusion_state"]),
                    comskip_state=str(row["comskip_local_state"]),
                )
            )
    if not points:
        raise ValueError(f"Sidecar {path} contains no observations")
    if any(right.time_seconds < left.time_seconds for left, right in zip(points, points[1:])):
        raise ValueError(f"Sidecar {path} is not time ordered")
    return metadata, points


class TimelineAggregator:
    def __init__(self, points: list[TimelinePoint]) -> None:
        self.points = points
        self.times = [point.time_seconds for point in points]

    def fractions(self, start: float, end: float, *, source: str = "fusion") -> Fractions:
        duration = max(0.0, end - start)
        totals = {PRESENT: 0.0, ABSENT: 0.0, CONFLICT: 0.0, UNKNOWN: 0.0}
        if duration == 0.0:
            return Fractions(0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        index = max(0, bisect.bisect_right(self.times, start) - 1)
        covered = 0.0
        while index < len(self.points) and self.points[index].time_seconds < end:
            point = self.points[index]
            segment_start = max(start, point.time_seconds)
            next_time = self.points[index + 1].time_seconds if index + 1 < len(self.points) else end
            segment_end = min(end, next_time)
            if segment_end > segment_start:
                state = point.fusion_state if source == "fusion" else point.comskip_state
                if state not in totals:
                    state = UNKNOWN
                segment = segment_end - segment_start
                totals[state] += segment
                covered += segment
            index += 1
        if covered < duration:
            totals[UNKNOWN] += duration - covered
        return Fractions(
            present=totals[PRESENT] / duration,
            absent=totals[ABSENT] / duration,
            conflict=totals[CONFLICT] / duration,
            unknown=totals[UNKNOWN] / duration,
            covered_seconds=covered,
            block_seconds=duration,
        )


def block_evidence(fractions: Fractions, logo_percentage_threshold: float) -> str:
    # Reuse Comskip's existing >25% present rule. Its complement is the only
    # conservative way to assert absence while CONFLICT/UNKNOWN remain neutral.
    if fractions.present > logo_percentage_threshold:
        return PRESENT
    if fractions.absent > 1.0 - logo_percentage_threshold:
        return ABSENT
    return NEUTRAL


def evidence_modifier(
    evidence: str,
    *,
    logo_present_modifier: float,
    punish_no_logo: bool,
) -> tuple[float, str]:
    if evidence == PRESENT:
        return logo_present_modifier, "logo_present_modifier"
    if evidence == ABSENT and punish_no_logo:
        return 2.0, "punish_no_logo"
    return 1.0, "neutral_logo_component"


def replace_logo_component(
    normal_score: float,
    normal_modifier: float,
    hybrid_modifier: float,
) -> float:
    if normal_modifier <= 0.0:
        raise ValueError("Normal logo modifier must be positive")
    return normal_score / normal_modifier * hybrid_modifier


def generate_shadow(
    *,
    threshold: float,
    blocks: list[NormalBlock],
    metadata: dict,
    points: list[TimelinePoint],
    logo_percentage_threshold: float,
    logo_present_modifier: float,
    punish_no_logo: bool,
) -> list[dict]:
    aggregator = TimelineAggregator(points)
    comskip_reliable = (
        metadata.get("global_reliability", {}).get("comskip") == "ACCEPTED_BY_EXISTING_GATE"
    )
    rows: list[dict] = []
    for block in blocks:
        fusion = aggregator.fractions(block.time_start, block.time_end, source="fusion")
        normal = aggregator.fractions(block.time_start, block.time_end, source="comskip")
        normal_evidence = block_evidence(normal, logo_percentage_threshold) if comskip_reliable else NEUTRAL
        hybrid_evidence = block_evidence(fusion, logo_percentage_threshold)
        normal_modifier, normal_reason = evidence_modifier(
            normal_evidence,
            logo_present_modifier=logo_present_modifier,
            punish_no_logo=punish_no_logo,
        )
        hybrid_modifier, hybrid_reason = evidence_modifier(
            hybrid_evidence,
            logo_present_modifier=logo_present_modifier,
            punish_no_logo=punish_no_logo,
        )
        shadow_score = replace_logo_component(
            block.normal_score,
            normal_modifier,
            hybrid_modifier,
        )
        normal_commercial = block.normal_score > threshold
        shadow_commercial = shadow_score > threshold
        rows.append(
            {
                **asdict(block),
                "normal_logo_state": normal_evidence,
                "normal_logo_fraction": normal.present,
                "normal_logo_modifier": normal_modifier,
                "normal_logo_modifier_reason": normal_reason,
                "hybrid_present_fraction": fusion.present,
                "hybrid_absent_fraction": fusion.absent,
                "hybrid_conflict_fraction": fusion.conflict,
                "hybrid_unknown_fraction": fusion.unknown,
                "hybrid_covered_seconds": fusion.covered_seconds,
                "hybrid_logo_evidence": hybrid_evidence,
                "hybrid_logo_modifier": hybrid_modifier,
                "hybrid_logo_modifier_reason": hybrid_reason,
                "hybrid_shadow_score": shadow_score,
                "normal_classification": "COMMERCIAL" if normal_commercial else "SHOW",
                "shadow_classification": "COMMERCIAL" if shadow_commercial else "SHOW",
                "classification_changed": normal_commercial != shadow_commercial,
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    if not 0.0 < args.logo_percentage_threshold < 1.0:
        raise ValueError("--logo-percentage-threshold must lie between zero and one")
    started = time.perf_counter()
    threshold, blocks = parse_comskip_log(args.comskip_log)
    metadata, points = load_sidecar(args.sidecar)
    rows = generate_shadow(
        threshold=threshold,
        blocks=blocks,
        metadata=metadata,
        points=points,
        logo_percentage_threshold=args.logo_percentage_threshold,
        logo_present_modifier=args.logo_present_modifier,
        punish_no_logo=args.punish_no_logo,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    elapsed = time.perf_counter() - started
    changed = [row for row in rows if row["classification_changed"]]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "method": "final_normal_score_with_existing_logo_component_replaced",
        "commercial_outputs_modified": False,
        "score_threshold": threshold,
        "logo_percentage_threshold": args.logo_percentage_threshold,
        "logo_present_modifier": args.logo_present_modifier,
        "punish_no_logo_modifier": 2.0 if args.punish_no_logo else 1.0,
        "comskip_global_reliability": metadata.get("global_reliability", {}).get("comskip"),
        "logofinder_global_reliability": metadata.get("global_reliability", {}).get("logofinder"),
        "block_count": len(rows),
        "classification_change_count": len(changed),
        "changed_blocks": [row["block"] for row in changed],
        "elapsed_seconds": elapsed,
        "source_log": str(args.comskip_log),
        "source_sidecar": str(args.sidecar),
    }
    summary_path = args.summary or args.output.with_name(args.output.stem + "-summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
