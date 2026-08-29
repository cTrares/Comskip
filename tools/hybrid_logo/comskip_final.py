from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

from multiwindow_logo_experiment import (
    DEFAULT_WINDOW_SECONDS,
    DIAGNOSTIC_NAME,
    FINAL_DIRECTORY_NAME,
    FINAL_OUTPUT_NAME,
    SELECTED_MASK_NAME,
    run_film,
)
from public_broadcaster_fast_mode import (
    CONFIG_NAME as FAST_MODE_CONFIG_NAME,
    DEFAULT_TIME_BUDGET_SECONDS,
    MARKER_NAME as FAST_MODE_MARKER_NAME,
    PROCESSING_MODE as FAST_PROCESSING_MODE,
    load_fast_mode_channels,
    run_public_broadcaster_fast_mode,
    selected_fast_mode_channel,
)
from commercial_macro_mode import (
    CONFIG_NAME as MACRO_MODE_CONFIG_NAME,
    DEFAULT_SAMPLE_SECONDS as DEFAULT_MACRO_SAMPLE_SECONDS,
    DEFAULT_TIME_BUDGET_SECONDS as DEFAULT_MACRO_TIME_BUDGET_SECONDS,
    MARKER_NAME as MACRO_MODE_MARKER_NAME,
    PROCESSING_MODE as MACRO_PROCESSING_MODE,
    load_macro_channels,
    run_commercial_macro_mode,
    selected_macro_channel,
)


VERSION = "Comskip V4 2026-08-30 commercial-logo-macro"
_ACTIVE_TRACE: "ExitTrace | None" = None
RUN_DIRECTORY_NAME = "r"
FILM_DIRECTORY_NAME = "run"
REVIEW_DIRECTORY_NAME = "review"
RUN_ID_BYTES = 5


class ExitTrace:
    def __init__(self, video: Path, run_id: str):
        trace_root = runtime_root() / "traces"
        trace_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.path = trace_root / f"{run_id}-{timestamp}.jsonl"
        self.started = time.perf_counter()
        self.mark("TRACE_STARTED", video=str(video), run_id=run_id, pid=os.getpid())

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
    parser.add_argument(
        "--wedo-movies-mode",
        choices=("off", "shadow", "active"),
        default="active",
        help="WeDo Movies special detector mode; ignored for filenames without exact 'wedo-movies'.",
    )
    parser.add_argument(
        "--commercial-edge-refiner-mode",
        choices=("off", "shadow", "active"),
        default="active",
        help="General fixed-position logo return check after final Comskip; active applies confirmed extensions.",
    )
    parser.add_argument(
        "--full-analysis",
        action="store_true",
        help="Ignore all fast modes and run the complete legacy analysis for this recording.",
    )
    parser.add_argument(
        "--fast-mode-time-budget",
        type=float,
        default=DEFAULT_TIME_BUDGET_SECONDS,
        help="Hard target in seconds for the public-broadcaster boundary finder.",
    )
    parser.add_argument(
        "--macro-mode",
        choices=("off", "active"),
        default="active",
        help="Commercial logo macro mode; the station list decides where active mode applies.",
    )
    parser.add_argument(
        "--macro-time-budget",
        type=float,
        default=DEFAULT_MACRO_TIME_BUDGET_SECONDS,
        help="Hard target in seconds for the commercial macro mode.",
    )
    parser.add_argument(
        "--macro-sample-seconds",
        type=float,
        default=DEFAULT_MACRO_SAMPLE_SECONDS,
        help="Finest global sampling interval for the commercial macro mode.",
    )
    parser.add_argument("--keep-work-dir", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="store_true")
    return parser.parse_args()


def runtime_root() -> Path:
    return Path(tempfile.gettempdir()) / "ComskipFinal"


def create_run_workspace(runs_root: Path) -> tuple[str, Path]:
    runs_root.mkdir(parents=True, exist_ok=True)
    for _attempt in range(100):
        run_id = secrets.token_hex(RUN_ID_BYTES)
        work_root = runs_root / run_id
        try:
            work_root.mkdir()
        except FileExistsError:
            continue
        return run_id, work_root
    raise RuntimeError(f"Could not allocate a unique short run workspace below {runs_root}")


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
        prefix=".cf-", suffix=".tmp", dir=destination.parent
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
        prefix=".cf-", suffix=".tmp", dir=destination.parent
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
    run_id: str | None = None,
) -> Path:
    diagnostic_root = runtime_root() / "diagnostics"
    diagnostic_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    diagnostic_id = run_id or secrets.token_hex(RUN_ID_BYTES)
    destination = diagnostic_root / f"{diagnostic_id}-{timestamp}.zip"
    temporary = destination.with_suffix(".tmp")
    failure = {
        "schema_version": 1,
        "workflow_version": VERSION,
        "run_id": diagnostic_id,
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
    final_root = film_root / FINAL_DIRECTORY_NAME
    final_txt = final_root / f"{FINAL_OUTPUT_NAME}.txt"
    if trace:
        trace.mark("FINAL_TXT_VALIDATION_START", path=str(final_txt))
    if not complete_comskip_txt(final_txt):
        raise RuntimeError(f"Final Comskip TXT is missing or incomplete for {video}")
    if trace:
        trace.mark("FINAL_TXT_VALIDATION_END", complete=True)
        trace.mark("PORTABLE_OUTPUTS_PREPARE", destination_dir=str(video.parent))
    copied: list[Path] = []
    for suffix in (".edl", ".log"):
        source = final_root / f"{FINAL_OUTPUT_NAME}{suffix}"
        if source.is_file():
            destination = video.with_suffix(suffix)
            atomic_copy(source, destination, trace=trace, label=suffix[1:].upper())
            copied.append(destination)
    selected_logo = film_root / SELECTED_MASK_NAME
    if selected_logo.is_file():
        destination = video.with_name(base + ".logo.txt")
        atomic_copy(selected_logo, destination, trace=trace, label="LOGO_TXT")
        copied.append(destination)
    fast_mode_marker = film_root / FAST_MODE_MARKER_NAME
    portable_fast_mode_marker = video.with_name(base + ".schnellmodus.txt")
    if fast_mode_marker.is_file():
        atomic_copy(
            fast_mode_marker,
            portable_fast_mode_marker,
            trace=trace,
            label="SCHNELLMODUS_TXT",
        )
        copied.append(portable_fast_mode_marker)
    elif result.get("processing_mode") != FAST_PROCESSING_MODE:
        portable_fast_mode_marker.unlink(missing_ok=True)
    macro_mode_marker = film_root / MACRO_MODE_MARKER_NAME
    portable_macro_mode_marker = video.with_name(base + ".makromodus.txt")
    if macro_mode_marker.is_file():
        atomic_copy(
            macro_mode_marker,
            portable_macro_mode_marker,
            trace=trace,
            label="MAKROMODUS_TXT",
        )
        copied.append(portable_macro_mode_marker)
    elif result.get("processing_mode") != MACRO_PROCESSING_MODE:
        portable_macro_mode_marker.unlink(missing_ok=True)
    diagnostic = film_root / DIAGNOSTIC_NAME
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

    runs_root = runtime_root() / RUN_DIRECTORY_NAME
    run_id, work_root = create_run_workspace(runs_root)
    trace = ExitTrace(video, run_id)
    _ACTIVE_TRACE = trace
    trace.mark(
        "RUNTIME_PATHS_VALIDATED",
        application_dir=str(application_dir()),
        comskip=str(args.comskip.resolve()),
        ini=str(args.ini.resolve()),
        ffmpeg=str(args.ffmpeg.resolve()),
        ffprobe=str(args.ffprobe.resolve()),
        run_id=run_id,
    )

    fast_mode_config = application_dir() / FAST_MODE_CONFIG_NAME
    try:
        fast_mode_channels = load_fast_mode_channels(fast_mode_config)
    except ValueError as exc:
        print(f"Schnellmodus-Konfiguration ungültig: {exc}", file=sys.stderr)
        return 2
    if not fast_mode_config.is_file():
        print(
            f"WARNUNG: {FAST_MODE_CONFIG_NAME} fehlt; Schnellmodus ist deaktiviert.",
            flush=True,
        )
    requested_full_analysis = bool(getattr(args, "full_analysis", False))
    fast_mode_channel = (
        None
        if requested_full_analysis
        else selected_fast_mode_channel(video, fast_mode_channels)
    )
    macro_mode_config = application_dir() / MACRO_MODE_CONFIG_NAME
    try:
        macro_mode_channels = load_macro_channels(macro_mode_config)
    except ValueError as exc:
        print(f"Makromodus-Konfiguration ungültig: {exc}", file=sys.stderr)
        return 2
    if not macro_mode_config.is_file():
        print(
            f"WARNUNG: {MACRO_MODE_CONFIG_NAME} fehlt; Makromodus ist deaktiviert.",
            flush=True,
        )
    requested_macro_mode = getattr(args, "macro_mode", "active")
    macro_mode_channel = (
        None
        if requested_full_analysis or requested_macro_mode == "off"
        else selected_macro_channel(video, macro_mode_channels)
    )

    is_wedo_movies = "wedo-movies" in video.name
    if is_wedo_movies:
        macro_mode_channel = None
    requested_wedo_movies_mode = getattr(args, "wedo_movies_mode", "active")
    wedo_movies_mode = requested_wedo_movies_mode if is_wedo_movies else "off"
    commercial_edge_refiner_mode = getattr(args, "commercial_edge_refiner_mode", "active")
    if is_wedo_movies:
        if wedo_movies_mode == "off":
            print("WeDo Movies erkannt - spezielles WeDo-Movies-Modul ist abgeschaltet.", flush=True)
        else:
            print(
                f"WeDo Movies erkannt - spezielles WeDo-Movies-Modul wird verwendet ({wedo_movies_mode}).",
                flush=True,
            )
    trace.mark(
        "STATION_PROFILE_SELECTED",
        station=(
            f"fast_boundary:{fast_mode_channel}"
            if fast_mode_channel
            else f"commercial_macro:{macro_mode_channel}"
            if macro_mode_channel
            else "wedo_movies" if is_wedo_movies else "default"
        ),
        wedo_movies_mode=wedo_movies_mode,
        commercial_edge_refiner_mode=commercial_edge_refiner_mode,
        fast_mode_channel=fast_mode_channel,
        macro_mode_channel=macro_mode_channel,
        macro_mode_config=str(macro_mode_config),
        fast_mode_config=str(fast_mode_config),
        filename=video.name,
    )

    run_args = argparse.Namespace(
        output_root=work_root,
        sight_root=work_root / REVIEW_DIRECTORY_NAME,
        film_dirname=FILM_DIRECTORY_NAME,
        comskip=args.comskip.resolve(),
        ini=args.ini.resolve(),
        ffmpeg=args.ffmpeg.resolve(),
        ffprobe=args.ffprobe.resolve(),
        window_seconds=args.window_seconds,
        resume_incomplete=False,
        wedo_movies_mode=wedo_movies_mode,
        commercial_edge_refiner_mode=commercial_edge_refiner_mode,
    )
    exit_code = 0
    try:
        run_args.output_root.mkdir(parents=True, exist_ok=True)
        run_args.sight_root.mkdir(parents=True)
        if fast_mode_channel:
            print("=" * 72, flush=True)
            print("SCHNELLMODUS AKTIV", flush=True)
            print(f"Sender: {fast_mode_channel}", flush=True)
            print("Nur zwei grobe Randblöcke; keine inneren Werbeblöcke.", flush=True)
            print("=" * 72, flush=True)
        elif macro_mode_channel:
            print("=" * 72, flush=True)
            print("MAKROMODUS AKTIV", flush=True)
            print(f"Sender: {macro_mode_channel}", flush=True)
            print("Dynamisches Logo, grobe Filmblöcke, lokale Kantenprüfung.", flush=True)
            print("=" * 72, flush=True)
        print(f"Comskip final: analysing {video.name}", flush=True)
        trace.mark("RUN_FILM_START", work_root=str(work_root))
        run_args.exit_trace = trace.mark
        if fast_mode_channel:
            result = run_public_broadcaster_fast_mode(
                video=video,
                film_root=run_args.output_root / run_args.film_dirname,
                ffmpeg=run_args.ffmpeg,
                ffprobe=run_args.ffprobe,
                channel=fast_mode_channel,
                config_path=fast_mode_config,
                time_budget_seconds=float(
                    getattr(args, "fast_mode_time_budget", DEFAULT_TIME_BUDGET_SECONDS)
                ),
            )
        elif macro_mode_channel:
            result = run_commercial_macro_mode(
                video=video,
                film_root=run_args.output_root / run_args.film_dirname,
                ffmpeg=run_args.ffmpeg,
                ffprobe=run_args.ffprobe,
                comskip=run_args.comskip,
                ini=run_args.ini,
                channel=macro_mode_channel,
                config_path=macro_mode_config,
                time_budget_seconds=float(
                    getattr(args, "macro_time_budget", DEFAULT_MACRO_TIME_BUDGET_SECONDS)
                ),
                sample_seconds=float(
                    getattr(args, "macro_sample_seconds", DEFAULT_MACRO_SAMPLE_SECONDS)
                ),
            )
        else:
            result = run_film(run_args, video.stem, video)
        trace.mark("RUN_FILM_RETURNED", final_stage=result.get("final_stage_intervals"))
        trace.mark("COPY_FINAL_OUTPUTS_START")
        copied = copy_final_outputs(video, run_args.output_root / FILM_DIRECTORY_NAME, result, trace=trace)
        trace.mark("COPY_FINAL_OUTPUTS_RETURNED")
        print("Comskip final: outputs " + ", ".join(path.name for path in copied), flush=True)
    except Exception as exc:
        print(f"Comskip final: {exc}", file=sys.stderr)
        trace.mark("MAIN_EXCEPTION", error_type=type(exc).__name__, error=str(exc))
        try:
            diagnostic = create_diagnostic_package(video, work_root, exc, trace=trace, run_id=run_id)
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
