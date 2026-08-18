from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

from multiwindow_logo_experiment import DEFAULT_WINDOW_SECONDS, run_film


VERSION = "Comskip custom final logo workflow 2026-08-18-puls-fix"
_ACTIVE_TRACE: "ExitTrace | None" = None


class ExitTrace:
    def __init__(self, video: Path):
        trace_root = runtime_root() / "traces"
        trace_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.path = trace_root / f"{video.stem}-{timestamp}.jsonl"
        self.started = time.perf_counter()
        self.mark("TRACE_STARTED", video=str(video), pid=os.getpid())

    def mark(self, stage: str, **details: object) -> None:
        record = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "elapsed_seconds": time.perf_counter() - self.started,
            "stage": stage,
            **details,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def executable_default(name: str) -> Path:
    sibling = application_dir() / name
    if getattr(sys, "frozen", False) or sibling.is_file():
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
    parser.add_argument("--keep-work-dir", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="store_true")
    return parser.parse_args()


def runtime_root() -> Path:
    return Path(tempfile.gettempdir()) / "ComskipFinal"


def atomic_copy(
    source: Path,
    destination: Path,
    *,
    trace: ExitTrace | None = None,
    label: str = "OUTPUT",
) -> None:
    if trace:
        trace.mark(f"{label}_PREPARE", source=str(source), destination=str(destination))
        trace.mark(f"{label}_PARENT_READY_CHECK_START")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if trace:
        trace.mark(f"{label}_PARENT_READY_CHECK_END")
        trace.mark(f"{label}_TEMP_CREATE_START")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    if trace:
        trace.mark(f"{label}_TEMP_CREATE_END", temporary=temporary_name)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        if trace:
            trace.mark(f"{label}_COPY_START", temporary=str(temporary))
        shutil.copy2(source, temporary)
        if trace:
            trace.mark(f"{label}_COPY_END", bytes=temporary.stat().st_size)
        os.replace(temporary, destination)
        if trace:
            trace.mark(f"{label}_ATOMIC_REPLACE_END")
    finally:
        temporary.unlink(missing_ok=True)
        if trace:
            trace.mark(f"{label}_TEMP_HANDLE_CLOSED")


def atomic_write_text(
    destination: Path,
    payload: str,
    *,
    trace: ExitTrace | None = None,
    label: str = "JSON",
) -> None:
    if trace:
        trace.mark(f"{label}_PARENT_READY_CHECK_START")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if trace:
        trace.mark(f"{label}_PARENT_READY_CHECK_END")
        trace.mark(f"{label}_TEMP_CREATE_START")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    if trace:
        trace.mark(f"{label}_TEMP_CREATE_END", temporary=temporary_name)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(payload, encoding="utf-8")
        if trace:
            trace.mark(f"{label}_WRITE_END", bytes=temporary.stat().st_size)
        os.replace(temporary, destination)
        if trace:
            trace.mark(f"{label}_ATOMIC_REPLACE_END")
    finally:
        temporary.unlink(missing_ok=True)
        if trace:
            trace.mark(f"{label}_TEMP_HANDLE_CLOSED")


def complete_comskip_txt(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        return handle.readline().startswith("FILE PROCESSING COMPLETE ")


def create_diagnostic_package(
    video: Path,
    work_root: Path,
    exc: BaseException,
    trace: ExitTrace | None = None,
) -> Path:
    diagnostic_root = runtime_root() / "diagnostics"
    diagnostic_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = diagnostic_root / f"{video.stem}-{timestamp}.zip"
    temporary = destination.with_suffix(".tmp")
    failure = {
        "schema_version": 1,
        "workflow_version": VERSION,
        "video": str(video),
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    allowed_suffixes = {".log", ".txt", ".edl", ".json"}
    try:
        if trace:
            trace.mark("DIAGNOSTIC_PACKAGE_START", temporary=str(temporary))
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("failure.json", json.dumps(failure, ensure_ascii=False, indent=2) + "\n")
            for path in sorted(work_root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
                    continue
                if trace:
                    trace.mark("DIAGNOSTIC_FILE_START", path=str(path), bytes=path.stat().st_size)
                archive.write(path, path.relative_to(work_root))
                if trace:
                    trace.mark("DIAGNOSTIC_FILE_END", path=str(path))
        os.replace(temporary, destination)
        if trace:
            trace.mark("DIAGNOSTIC_PACKAGE_END", destination=str(destination))
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def copy_final_outputs(
    video: Path,
    film_root: Path,
    result: dict,
    trace: ExitTrace | None = None,
) -> list[Path]:
    base = video.stem
    final_root = film_root / "final"
    final_txt = final_root / f"{base}.txt"
    if trace:
        trace.mark("FINAL_TXT_VALIDATION_START", path=str(final_txt))
    if not complete_comskip_txt(final_txt):
        raise RuntimeError(f"Final Comskip TXT is missing or incomplete for {video}")
    if trace:
        trace.mark("FINAL_TXT_VALIDATION_END", complete=True)
        trace.mark("PORTABLE_OUTPUTS_PREPARE", destination_dir=str(video.parent))
    copied: list[Path] = []
    for suffix in (".edl", ".log"):
        source = final_root / f"{base}{suffix}"
        if source.is_file():
            destination = video.with_suffix(suffix)
            atomic_copy(source, destination, trace=trace, label=suffix[1:].upper())
            copied.append(destination)
    selected_logo = film_root / "selected-comskip-logo.txt"
    if selected_logo.is_file():
        destination = video.with_name(base + ".logo.txt")
        atomic_copy(selected_logo, destination, trace=trace, label="LOGO_TXT")
        copied.append(destination)
    diagnostic = film_root / "multiwindow_diagnostic.json"
    if diagnostic.is_file():
        destination = video.with_name(base + ".comskip-final.json")
        payload = json.loads(diagnostic.read_text(encoding="utf-8"))
        planned_txt = video.with_suffix(".txt")
        payload["portable_outputs"] = [str(path) for path in [*copied, planned_txt]]
        atomic_write_text(
            destination,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            trace=trace,
            label="DIAGNOSTIC_JSON",
        )
        copied.append(destination)
    destination_txt = video.with_suffix(".txt")
    if trace:
        trace.mark("TXT_PUBLISH_PREPARE", destination=str(destination_txt))
    atomic_copy(final_txt, destination_txt, trace=trace, label="TXT")
    copied.append(destination_txt)
    if trace:
        trace.mark("COPY_FINAL_OUTPUTS_END", copied=[str(path) for path in copied])
    return copied


def main() -> int:
    global _ACTIVE_TRACE
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

    trace = ExitTrace(video)
    _ACTIVE_TRACE = trace
    trace.mark(
        "RUNTIME_PATHS_VALIDATED",
        application_dir=str(application_dir()),
        comskip=str(args.comskip.resolve()),
        ini=str(args.ini.resolve()),
        ffmpeg=str(args.ffmpeg.resolve()),
        ffprobe=str(args.ffprobe.resolve()),
    )

    runs_root = runtime_root() / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix=f"{video.stem}-", dir=runs_root))
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
    exit_code = 0
    try:
        run_args.output_root.mkdir(parents=True)
        run_args.sight_root.mkdir(parents=True)
        print(f"Comskip final: analysing {video.name}", flush=True)
        trace.mark("RUN_FILM_START", work_root=str(work_root))
        run_args.exit_trace = trace.mark
        result = run_film(run_args, video.stem, video)
        trace.mark("RUN_FILM_RETURNED", final_stage=result.get("final_stage_intervals"))
        trace.mark("COPY_FINAL_OUTPUTS_START")
        copied = copy_final_outputs(video, run_args.output_root / video.stem, result, trace=trace)
        trace.mark("COPY_FINAL_OUTPUTS_RETURNED")
        print("Comskip final: outputs " + ", ".join(path.name for path in copied), flush=True)
    except Exception as exc:
        print(f"Comskip final: {exc}", file=sys.stderr)
        trace.mark("MAIN_EXCEPTION", error_type=type(exc).__name__, error=str(exc))
        try:
            diagnostic = create_diagnostic_package(video, work_root, exc, trace=trace)
            print(f"Diagnostic package: {diagnostic}", file=sys.stderr)
        except Exception as diagnostic_exc:
            print(f"Could not create diagnostic package: {diagnostic_exc}", file=sys.stderr)
        exit_code = 1
    finally:
        trace.mark(
            "FINALLY_BEGIN",
            threads=[thread.name for thread in threading.enumerate()],
        )
        try:
            cleanup_started = time.perf_counter()
            trace.mark("WORKSPACE_CLEANUP_START", work_root=str(work_root))
            shutil.rmtree(work_root)
            trace.mark("WORKSPACE_CLEANUP_END", cleanup_seconds=time.perf_counter() - cleanup_started)
        except FileNotFoundError:
            pass
        except Exception as cleanup_exc:
            print(f"Comskip final: could not remove temporary workspace: {cleanup_exc}", file=sys.stderr)
            exit_code = 1
        try:
            runs_root.rmdir()
        except OSError:
            pass
        trace.mark(
            "FINALLY_END",
            threads=[thread.name for thread in threading.enumerate()],
        )
    if args.keep_work_dir and exit_code == 0:
        print("--keep-work-dir is deprecated; successful workspaces are always removed.", file=sys.stderr)
    trace.mark("COMSKIP_FINAL_MAIN_RETURN", exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    _exit_code = main()
    if _ACTIVE_TRACE is not None:
        _ACTIVE_TRACE.mark("PROCESS_EXIT_IMMINENT", exit_code=_exit_code)
    raise SystemExit(_exit_code)
