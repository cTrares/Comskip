"""Standalone two-recording diagnosis of the unchanged v3 discovery gate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import math
import shutil
import sys
import time
import traceback
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import wedo_sparse_mode as sparse

VERSION = "WeDo Rueckfall-Diagnose 1 / v3 discovery"
TARGETS = (
    "2026-09-04_04-35_Barbarian-Queen_wedo-movies_hd.mp4",
    "2026-09-07_11-11_London-Town_wedo-movies_hd.mp4",
)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_image(path, frame):
    ok, encoded = sparse.cv2.imencode(".png", frame)
    if not ok:
        raise RuntimeError(f"Diagnosebild konnte nicht erzeugt werden: {path}")
    path.write_bytes(encoded.tobytes())


def gate_details(observations, windows, coverage):
    if not windows:
        reason = "NO_CANDIDATE_WINDOWS"
    elif coverage > sparse.MAX_LOCAL_COVERAGE:
        reason = "LOCAL_COVERAGE_EXCEEDED"
    else:
        reason = "LOCAL_SCAN_ACCEPTED"
    return {
        "reason": reason, "would_fall_back_at_discovery": reason != "LOCAL_SCAN_ACCEPTED",
        "coverage": coverage, "coverage_limit": sparse.MAX_LOCAL_COVERAGE,
        "comparison": "coverage > limit (strict)", "windows_seconds": windows,
        "sample_count": len(observations),
        "logo_absent_samples": sum(not row["logo_present"] for row in observations),
        "red_layout_samples": sum(row["red_layout"] for row in observations),
        "logo_absent_without_red_samples": sum(not row["logo_present"] and not row["red_layout"] for row in observations),
        "red_with_logo_present_samples": sum(row["logo_present"] and row["red_layout"] for row in observations),
    }


def window_evidence(observations, duration, candidates):
    variants = {}
    for name, rows in (
        ("actual_v3", observations),
        ("red_only_explanation_not_applied", [{**r, "logo_present": True} for r in observations]),
        ("logo_only_explanation_not_applied", [{**r, "red_layout": False} for r in observations]),
    ):
        windows = sparse.candidate_windows(rows, duration)
        variants[name] = {"windows_seconds": windows,
                          "coverage": sum(min(b, duration) - a for a, b in windows) / duration}
    actual = variants["actual_v3"]["windows_seconds"]
    checks = [{"candidate_number": i + 1, "first_layout_second": c["first_layout_second"],
               "last_layout_second": c["last_layout_second"],
               "fully_inside_discovery_window": any(a <= c["first_layout_second"] and c["last_layout_second"] < b
                                                    for a, b in actual)}
              for i, c in enumerate(candidates)]
    return {"variants": variants, "full_layout_candidate_coverage": checks,
            "note": "Counterfactual variants explain window size only; no detection rules are changed."}


def save_reference(score_at_times, root):
    # Read-only inspection of the actual scorer used by v3, not a rebuilt approximation.
    reference = inspect.getclosurevars(score_at_times).nonlocals.get("reference")
    if reference is None:
        return {"status": "REFERENCE_NOT_EXPOSED"}
    detail = {"status": "EXPORTED", "overlay": asdict(reference.overlay)}
    for name in ("gray", "edges", "edge_mask", "template_mask"):
        save_image(root / f"reference-{name}.png", getattr(reference, name))
    return detail


def diagnose_film(video: Path, output: Path, portable: Path):
    started = time.perf_counter()
    output.mkdir()
    capture = None
    result = {"video": str(video), "version": VERSION, "status": "STARTED", "timings_seconds": {}}

    def checkpoint():
        result["elapsed_seconds"] = time.perf_counter() - started
        write_json(output / "diagnostic.json", result)

    try:
        stat = video.stat()
        result["input_file"] = {"size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        result["settings"] = {"sample_seconds": sparse.SAMPLE_SECONDS,
                              "logo_present_threshold": sparse.PRESENT_THRESHOLD,
                              "coverage_limit": sparse.MAX_LOCAL_COVERAGE,
                              "window_padding_seconds": math.ceil(sparse.WedoMoviesConfig().max_break_seconds + sparse.SAMPLE_SECONDS),
                              "layout": asdict(sparse.WedoMoviesConfig())}
        metadata = sparse.probe_video(portable / "ffprobe.exe", video)
        result["metadata"] = asdict(metadata)
        duration = min(metadata.duration_seconds, metadata.total_frames / metadata.fps)
        result["last_valid_frame_seconds"] = sparse.last_frame_seconds(metadata.total_frames, metadata.fps)
        existing = output / "existing-results"
        existing.mkdir()
        for suffix in (".comskip-final.json", ".txt", ".edl", ".log", ".logo.txt"):
            source = video.with_name(video.stem + suffix)
            if source.is_file():
                shutil.copyfile(source, existing / source.name)
        checkpoint()
        print("  [1/3] Logo mit dem unveränderten v3-Lernweg lernen", flush=True)
        stage = time.perf_counter()
        capture, scorer, typical, learning = sparse.learn_macro_overlay_via_comskip(
            video=video, metadata=metadata, film_root=output, ffmpeg=portable / "ffmpeg.exe",
            comskip=portable / "comskip.exe", ini=portable / "comskip.ini")
        result["timings_seconds"]["logo_learning"] = time.perf_counter() - stage
        result["learning"] = learning
        result["typical_score"] = typical
        if scorer is None or typical is None or typical < sparse.PRESENT_THRESHOLD:
            result.update(status="DIAGNOSED", discovery={"reason": "LOGO_LEARNING_UNRELIABLE", "would_fall_back_at_discovery": True})
            checkpoint()
            return result
        result["reference"] = save_reference(scorer, output)
        print("  [2/3] Alle Logo-/Layout-Stichproben, Bilder und Suchfenster protokollieren", flush=True)
        images = output / "samples"
        images.mkdir()
        rect = learning.get("rect_discovered_for_this_recording")
        stage = time.perf_counter()
        callback_seconds = 0.0
        with (output / "samples.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["seconds", "logo_score", "logo_present", "red_layout",
                "trigger", "top_red_fraction", "bottom_red_fraction", "bottom_left_texture", "window_start", "window_end",
                "within_first_or_last_six_minutes", "frame_png", "logo_crop_png"])
            writer.writeheader()

            def observation(row, frame, small, layout):
                nonlocal callback_seconds
                begin = time.perf_counter()
                second = row["seconds"]
                stem = f"{int(second):06d}"
                save_image(images / f"{stem}.png", small)
                crop_name = ""
                if rect:
                    a, b, c, d = map(int, rect)
                    crop = frame[max(0, b):min(d, frame.shape[0]), max(0, a):min(c, frame.shape[1])]
                    if crop.size:
                        crop_name = f"samples/{stem}-logo.png"
                        save_image(output / crop_name, crop)
                padding = result["settings"]["window_padding_seconds"]
                trigger = not row["logo_present"] or row["red_layout"]
                writer.writerow({**row, "trigger": trigger,
                    "top_red_fraction": layout.top_red_fraction, "bottom_red_fraction": layout.bottom_red_fraction,
                    "bottom_left_texture": layout.bottom_left_texture,
                    "window_start": max(0, math.floor(second-padding)) if trigger else "",
                    "window_end": min(math.ceil(duration), math.ceil(second+padding)) if trigger else "",
                    "within_first_or_last_six_minutes": second < 360 or second > duration-360,
                    "frame_png": f"samples/{stem}.png", "logo_crop_png": crop_name})
                handle.flush()
                callback_seconds += time.perf_counter() - begin

            observations, windows, coverage = sparse.coarse_discovery(video, metadata, scorer, on_observation=observation)
        result["timings_seconds"]["coarse_scan_including_diagnostic_images"] = time.perf_counter() - stage
        result["timings_seconds"]["diagnostic_image_and_csv_writes"] = callback_seconds
        result["observations"] = observations
        result["discovery"] = gate_details(observations, windows, coverage)
        result["window_sources"] = [{"start_seconds": a, "end_seconds": b,
            "trigger_seconds": [r["seconds"] for r in observations
                                if (not r["logo_present"] or r["red_layout"]) and a <= r["seconds"] <= b]}
                                   for a, b in windows]
        checkpoint()
        print(f"  Entscheidung: {result['discovery']['reason']} | {len(windows)} Fenster | "
              f"{coverage:.2%} Abdeckung (Grenze {sparse.MAX_LOCAL_COVERAGE:.0%})", flush=True)
        print("  [3/3] Rotes Layout als unabhängige Kontrolle über die Aufnahme prüfen", flush=True)
        stage = time.perf_counter()
        layout = sparse.scan_layout_windows(video, portable / "ffmpeg.exe", [(0, math.ceil(duration))], duration, output)
        result["timings_seconds"]["full_red_layout_control"] = time.perf_counter() - stage
        result["full_red_layout_control"] = layout
        result["window_evidence"] = window_evidence(observations, duration, layout["candidates"])
        result["status"] = "DIAGNOSED"
    except Exception:
        result["status"] = "ERROR"
        result["error"] = traceback.format_exc()
        (output / "error.log").write_text(result["error"], encoding="utf-8")
        print(f"  Diagnosefehler; Einzelheiten werden mit eingepackt: {output / 'error.log'}", flush=True)
    finally:
        if capture is not None:
            capture.release()
        # Only generated learning clips under this unique diagnostic output are removed.
        # Input MP4s are outside this directory and are never modified.
        for clip in (output / "macro-comskip-logo").rglob("*.mp4"):
            if clip.resolve().is_relative_to(output.resolve()):
                clip.unlink()
        checkpoint()
    return result


def selected_videos(directory):
    # Exact known recording names; no wildcard search, recursion or other movies.
    selected = [directory / name for name in TARGETS]
    missing = [str(p) for p in selected if not p.is_file()]
    if missing:
        raise FileNotFoundError("Diese beiden Originaldateien werden benötigt:\n" + "\n".join(missing))
    return selected


def create_bundle(output):
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(output.rglob("*")):
            if source.is_file() and source.suffix.lower() != ".mp4":
                bundle.write(source, source.relative_to(output).as_posix())
    return archive


def main():
    parser = argparse.ArgumentParser(description="Nur Barbarian Queen und London Town: v3-Rückfall ohne alte Vollanalyse diagnostizieren.")
    parser.add_argument("directory", nargs="?", type=Path, help="Ordner mit den beiden Original-MP4s")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(VERSION)
        return 0
    directory = args.directory
    if directory is None:
        entered = input("Ordner mit den beiden Filmen hier eingeben oder hineinziehen, dann Enter: ").strip().strip('"')
        if not entered:
            print("Abgebrochen.")
            return 2
        directory = Path(entered)
    directory = directory.resolve()
    portable = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2] / "dist/ComSkip"
    try:
        videos = selected_videos(directory)
        for name in ("ffmpeg.exe", "ffprobe.exe", "comskip.exe", "comskip.ini"):
            if not (portable / name).is_file():
                raise FileNotFoundError(str(portable / name))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = directory / ("WeDo-Rueckfall-Diagnose-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    output.mkdir()
    manifest = {"version": VERSION, "created": datetime.now().astimezone().isoformat(),
                "scope": "Only discovery diagnosis plus full red-layout control; no native tail scan, legacy run, or cut output.",
                "tools_sha256": {name: hashlib.sha256((portable/name).read_bytes()).hexdigest()
                                 for name in ("ffmpeg.exe", "ffprobe.exe", "comskip.exe", "comskip.ini")}, "films": []}
    shutil.copyfile(portable / "comskip.ini", output / "comskip.ini")
    write_json(output / "manifest.json", manifest)
    print(VERSION, flush=True)
    try:
        for index, video in enumerate(videos, 1):
            print(f"[{index}/2] {video.name}", flush=True)
            result = diagnose_film(video, output / video.stem, portable)
            manifest["films"].append({"video": video.name, "status": result["status"],
                "discovery": result.get("discovery"), "elapsed_seconds": result["elapsed_seconds"]})
            write_json(output / "manifest.json", manifest)
    except KeyboardInterrupt:
        manifest["interrupted"] = True
        print("Abgebrochen. Vorhandene Diagnosedaten werden eingepackt.", flush=True)
    finally:
        write_json(output / "manifest.json", manifest)
        summary = ["WeDo-Rückfall-Diagnose", "", "Keine Videos oder bestehenden Schnittdateien verändert.",
                   "Diagnosebilder und Kontrollscan verursachen Zusatzaufwand; Laufzeiten nicht direkt mit v3 vergleichen.", ""]
        for film in manifest["films"]:
            decision = film.get("discovery") or {}
            summary.append(f"{film['video']}: {film['status']} / {decision.get('reason', 'siehe Fehlerprotokoll')}")
        summary += ["", "Inhalt: Einstellungen, Tool-Prüfsummen, vorhandene Ergebnisse, Lernmasken und Lernprotokolle,",
                    "tatsächliche Logo-Referenz, sämtliche Stichproben mit Bildern/Logo-Ausschnitten, Suchfenster,",
                    "genauer Rückfallgrund und unabhängiger Rotlayout-Kontrollscan."]
        (output / "LESEN.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
        archive = create_bundle(output)
        print(f"\nDieses ZIP bitte zurückgeben:\n{archive}", flush=True)
    return 0 if len(manifest["films"]) == 2 and all(f["status"] == "DIAGNOSED" for f in manifest["films"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
