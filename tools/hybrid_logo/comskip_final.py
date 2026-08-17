from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from multiwindow_logo_experiment import DEFAULT_WINDOW_SECONDS, run_film


VERSION = "Comskip custom final logo workflow 2026-08-18"


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def executable_default(name: str) -> Path:
    sibling = application_dir() / name
    if sibling.is_file():
        return sibling
    discovered = shutil.which(name)
    return Path(discovered) if discovered else sibling


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the released recurring-mask plus internal-logo-sensor Comskip workflow."
    )
    parser.add_argument("video", nargs="?", type=Path)
    parser.add_argument("--comskip", type=Path, default=executable_default("comskip.exe"))
    parser.add_argument("--ini", type=Path, default=application_dir() / "comskip.ini")
    parser.add_argument("--ffmpeg", type=Path, default=executable_default("ffmpeg.exe"))
    parser.add_argument("--ffprobe", type=Path, default=executable_default("ffprobe.exe"))
    parser.add_argument("--window-seconds", type=float, default=DEFAULT_WINDOW_SECONDS)
    parser.add_argument("--keep-work-dir", action="store_true")
    parser.add_argument("--version", action="store_true")
    return parser.parse_args()


def copy_final_outputs(video: Path, film_root: Path, result: dict) -> list[Path]:
    base = video.stem
    final_root = film_root / "final"
    copied: list[Path] = []
    for suffix in (".txt", ".edl", ".log"):
        source = final_root / f"{base}{suffix}"
        if source.is_file():
            destination = video.with_suffix(suffix)
            shutil.copy2(source, destination)
            copied.append(destination)
    selected_logo = film_root / "selected-comskip-logo.txt"
    if selected_logo.is_file():
        destination = video.with_name(base + ".logo.txt")
        shutil.copy2(selected_logo, destination)
        copied.append(destination)
    diagnostic = film_root / "multiwindow_diagnostic.json"
    if diagnostic.is_file():
        destination = video.with_name(base + ".comskip-final.json")
        payload = json.loads(diagnostic.read_text(encoding="utf-8"))
        payload["portable_outputs"] = [str(path) for path in copied]
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        copied.append(destination)
    if video.with_suffix(".txt") not in copied:
        raise RuntimeError(f"Final Comskip TXT was not produced for {video}")
    return copied


def main() -> int:
    args = parse_args()
    if args.version:
        print(VERSION)
        return 0
    if args.video is None:
        print("A video file is required.", file=sys.stderr)
        return 2
    video = args.video.resolve()
    required = (video, args.comskip.resolve(), args.ini.resolve(), args.ffmpeg.resolve(), args.ffprobe.resolve())
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("Required file not found: " + ", ".join(missing), file=sys.stderr)
        return 2

    work_root = Path(tempfile.mkdtemp(prefix=f".{video.stem}-comskip-", dir=video.parent))
    run_args = argparse.Namespace(
        output_root=work_root / "run",
        sight_root=work_root / "review",
        comskip=args.comskip.resolve(),
        ini=args.ini.resolve(),
        ffmpeg=args.ffmpeg.resolve(),
        ffprobe=args.ffprobe.resolve(),
        window_seconds=args.window_seconds,
        resume_incomplete=False,
    )
    try:
        run_args.output_root.mkdir(parents=True)
        run_args.sight_root.mkdir(parents=True)
        print(f"Comskip final: analysing {video.name}", flush=True)
        result = run_film(run_args, video.stem, video)
        copied = copy_final_outputs(video, run_args.output_root / video.stem, result)
        print("Comskip final: outputs " + ", ".join(path.name for path in copied), flush=True)
    except Exception as exc:
        print(f"Comskip final: {exc}", file=sys.stderr)
        print(f"Diagnostic work directory retained: {work_root}", file=sys.stderr)
        return 1
    if args.keep_work_dir:
        print(f"Diagnostic work directory retained: {work_root}")
    else:
        shutil.rmtree(work_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
