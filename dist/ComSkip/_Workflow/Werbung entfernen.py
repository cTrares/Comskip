# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None

BUILD_ID = "2026-08-30-COMSKIP-V4-SESSION-FOLDER-COMPACT-PHASES"
APPROVED_SUFFIX = "_Avidemux.py"
START_SUFFIX = "_Avidemux_Start.bat"
CROP_SUFFIX = "_Avidemux_CROP.py"
CROP_START_SUFFIX = "_Avidemux_CROP_Start.bat"
MANUAL_SUFFIX = "_Comskip_MANUELL.txt"
MANUAL_START_SUFFIX = "_Avidemux_MANUELL_Start.bat"

COMSKIP_PROGRESS_RE = re.compile(
    r"\b\d+\s+frames\s+in\s+[\d.]+\s+sec.*?,\s*(\d{1,3})%\s*$",
    re.IGNORECASE,
)

PHASE_RE = re.compile(r"^\[Phase\s+(\d+)/(\d+)\]", re.IGNORECASE)
TIMESTAMP_PREFIX_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-(?:\d{2}-)?", re.IGNORECASE
)
RECORDING_SUFFIX_RE = re.compile(r"_[^_]+_(?:hd|hq)$", re.IGNORECASE)

ANSI_BRIGHT_GREEN = "\x1b[92m"
ANSI_BLUE = "\x1b[94m"
ANSI_RED = "\x1b[91m"
ANSI_RESET = "\x1b[0m"

_SESSION_DIRECTORY = None

ANALYSIS_OUTPUT_SUFFIXES = (
    ".txt",
    ".edl",
    ".log",
    ".logo.txt",
    ".comskip-final.json",
    ".schnellmodus.txt",
)

DECISION_ARTIFACT_SUFFIXES = (
    CROP_SUFFIX,
    CROP_START_SUFFIX,
    MANUAL_SUFFIX,
    MANUAL_START_SUFFIX,
    APPROVED_SUFFIX,
    START_SUFFIX,
)

REANALYSIS_BACKUP_DIRECTORY = "_Comskip_Reanalyse_Sicherungen"


class ReturnToMainMenu(Exception):
    """Internal control flow after a requested batch/analysis stop."""


@dataclass(frozen=True)
class AnalysisProcessResult:
    returncode: int
    stop_after_current: bool = False
    aborted: bool = False


def configure_console():
    """Use real UTF-8 and ANSI colours in Windows Terminal."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def colour(text, ansi_code):
    if getattr(sys.stdout, "isatty", lambda: False)():
        return f"{ansi_code}{text}{ANSI_RESET}"
    return text


def compact_video_label(video_name):
    label = Path(video_name).stem
    label = TIMESTAMP_PREFIX_RE.sub("", label)
    label = RECORDING_SUFFIX_RE.sub("", label)
    label = label.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", label).strip() or Path(video_name).stem


def decode_child_output(raw_line):
    if isinstance(raw_line, str):
        return raw_line
    try:
        return raw_line.decode("utf-8")
    except UnicodeDecodeError:
        return raw_line.decode("cp1252", errors="replace")


class WindowsProcessJob:
    """Private kill-on-close job containing only one analysis process tree."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self, process):
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._ctypes = ctypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        self._kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        self._kernel32.AssignProcessToJobObject.argtypes = (
            wintypes.HANDLE,
            wintypes.HANDLE,
        )
        self._kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        self.handle = self._kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            information = ExtendedLimitInformation()
            information.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self._kernel32.SetInformationJobObject(
                self.handle,
                self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(information),
                ctypes.sizeof(information),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self._kernel32.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def terminate(self):
        if self.handle and not self._kernel32.TerminateJobObject(self.handle, 1):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def close(self):
        if self.handle:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


def downloads_folder():
    if winreg is not None:
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            guid = "{374DE290-123F-4565-9164-39C4925E467B}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, guid)
                return Path(os.path.expandvars(value)).expanduser()
        except OSError:
            pass
    return Path.home() / "Downloads"


def find_videos(downloads):
    return sorted(downloads.glob("*.mp4"), key=lambda p: p.name.lower())


def choose_session_folder(current_directory):
    """Choose a working directory without changing the permanent default."""
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="Arbeitsverzeichnis für diesen Durchlauf wählen",
            initialdir=str(current_directory),
            mustexist=True,
            parent=root,
        )
    except Exception as exc:
        print(f"FEHLER: Verzeichnisauswahl konnte nicht geöffnet werden: {exc}")
        return current_directory
    finally:
        if root is not None:
            root.destroy()

    if not selected:
        print("Verzeichnisauswahl abgebrochen; Arbeitsordner bleibt unverändert.")
        return current_directory

    chosen = Path(selected).resolve()
    print("Arbeitsordner für diesen Durchlauf:", chosen)
    return chosen


def is_complete_comskip_txt(path):
    if not path.exists():
        return False
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return bool(lines) and lines[0].startswith("FILE PROCESSING COMPLETE")
    except Exception:
        return False


def parse_comskip_txt(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    m = re.search(
        r"FILE PROCESSING COMPLETE\s+(\d+)\s+FRAMES\s+AT\s+(\d+)",
        lines[0] if lines else "",
    )
    if not m:
        raise ValueError("Comskip-TXT unvollständig oder unbekanntes Format.")

    total_frames, rate100 = int(m.group(1)), int(m.group(2))
    ads = []
    for line in lines[1:]:
        m2 = re.match(r"\s*(\d+)\s+(\d+)\s*$", line)
        if m2:
            a, b = map(int, m2.groups())
            if b < a:
                a, b = b, a
            ads.append((a, b))

    if ads and ads[-1][1] == ads[-1][0] + 1 and ads[-1][1] == total_frames:
        ads.pop()

    ads = [(max(0, a), min(total_frames, b)) for a, b in ads]

    ads.sort()
    merged = []
    for a, b in ads:
        if not merged or a > merged[-1][1] + 1:
            merged.append([a, b])
        else:
            merged[-1][1] = max(merged[-1][1], b)

    return total_frames, rate100, [(a, b) for a, b in merged]


def format_elapsed(seconds):
    total = max(0, int(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=3)
        except Exception:
            pass


def stop_process_tree(process):
    """Stop only the process group/tree rooted at this concrete analysis PID."""
    if process is None or process.poll() is not None:
        return

    if os.name == "nt":
        job = getattr(process, "_workflow_job", None)
        if job is not None:
            try:
                job.terminate()
                process.wait(timeout=5)
                return
            except (KeyboardInterrupt, Exception):
                pass
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            process.wait(timeout=5)
            return
        except (KeyboardInterrupt, Exception):
            pass

    try:
        process.terminate()
        process.wait(timeout=2)
    except (KeyboardInterrupt, Exception):
        try:
            process.kill()
            process.wait(timeout=3)
        except (KeyboardInterrupt, Exception):
            pass


def analysis_output_paths(video):
    return [video.with_name(video.stem + suffix) for suffix in ANALYSIS_OUTPUT_SUFFIXES]


def decision_artifact_paths(video):
    return [video.with_name(video.stem + suffix) for suffix in DECISION_ARTIFACT_SUFFIXES]


def stage_reanalysis_artifacts(video):
    """Move only this film's current analysis/review files into a recoverable backup."""
    sources = [
        path
        for path in (*analysis_output_paths(video), *decision_artifact_paths(video))
        if path.is_file()
    ]
    if not sources:
        return None, []

    stamp = time.strftime("%Y%m%d-%H%M%S")
    unique = f"{time.time_ns() % 1_000_000_000:09d}"
    backup = video.parent / REANALYSIS_BACKUP_DIRECTORY / f"{stamp}-{unique}"
    backup.mkdir(parents=True)
    moved = []
    try:
        for source in sources:
            destination = backup / source.name
            source.replace(destination)
            moved.append((source, destination))
    except BaseException:
        restore_staged_reanalysis_artifacts(backup, moved)
        raise
    return backup, moved


def restore_staged_reanalysis_artifacts(backup, moved):
    """Discard partial new results and restore the exact files moved before reanalysis."""
    for original, staged in reversed(moved):
        original.unlink(missing_ok=True)
        if staged.is_file():
            staged.replace(original)
    if backup is not None:
        try:
            backup.rmdir()
            backup.parent.rmdir()
        except OSError:
            pass


def snapshot_analysis_outputs(video):
    snapshot = {}
    for path in analysis_output_paths(video):
        if path.is_file():
            stat = path.stat()
            snapshot[path] = (path.read_bytes(), stat.st_atime_ns, stat.st_mtime_ns)
        else:
            snapshot[path] = None
    return snapshot


def restore_analysis_outputs(snapshot):
    """Restore prior user files and remove only outputs newly created by this run."""
    for path, original in snapshot.items():
        if original is None:
            path.unlink(missing_ok=True)
            continue
        payload, access_ns, modified_ns = original
        if path.is_file() and path.read_bytes() == payload:
            continue
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".restore", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            os.utime(path, ns=(access_ns, modified_ns))
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def poll_analysis_key():
    if os.name != "nt":
        return None
    import msvcrt

    while msvcrt.kbhit():
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            if msvcrt.kbhit():
                msvcrt.getwch()
            continue
        key = key.lower()
        if key in ("b", "x"):
            return key
    return None


def _read_process_lines(stream, lines):
    try:
        for line in stream:
            lines.put(line)
    finally:
        lines.put(None)


def process_has_visible_window(process_id):
    """Prueft unter Windows, ob der Prozess noch ein sichtbares Fenster hat."""
    if os.name != "nt":
        return True

    import ctypes
    from ctypes import wintypes

    found = False
    user32 = ctypes.windll.user32
    enum_proc_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def enum_proc(hwnd, _lparam):
        nonlocal found
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == process_id and user32.IsWindowVisible(hwnd):
            found = True
            return False
        return True

    user32.EnumWindows(enum_proc_type(enum_proc), 0)
    return found


def run_comskip_gui(gui, txt, downloads):
    """Startet ComskipGUI und faengt den bekannten Haenger nach Schliessen per X ab."""
    fast_mode_marker = txt.with_name(txt.stem + ".schnellmodus.txt")
    if fast_mode_marker.is_file():
        print("=" * 72)
        print("SCHNELLMODUS: zwei grobe Randblöcke, keine innere Werbesuche")
        print("M/N: Blockgrenze wechseln | Filmanfang suchen + E | Filmende suchen + B")
        print("=" * 72)
    process = subprocess.Popen([str(gui), str(txt)], cwd=str(downloads))

    if os.name != "nt":
        return process.wait()

    seen_window = False
    missing_since = None

    try:
        while True:
            returncode = process.poll()
            if returncode is not None:
                return returncode

            if process_has_visible_window(process.pid):
                seen_window = True
                missing_since = None
            elif seen_window:
                if missing_since is None:
                    missing_since = time.monotonic()
                elif time.monotonic() - missing_since >= 1.0:
                    print("ComskipGUI-Fenster wurde geschlossen; GUI-Prozess wird beendet.")
                    stop_process(process)
                    return process.returncode

            time.sleep(0.1)
    except KeyboardInterrupt:
        stop_process(process)
        raise


def run_analysis_command(command, cwd, index, total, video_name, key_reader=poll_analysis_key):
    started = time.monotonic()
    process = None
    reader = None
    lines = queue.Queue()
    last_phase = None
    stop_after_current = False
    aborted = False

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    label = compact_video_label(video_name)
    print(colour(f"[{index}/{total}] START  {label}", ANSI_BRIGHT_GREEN))

    child_environment = os.environ.copy()
    child_environment["PYTHONIOENCODING"] = "utf-8"
    child_environment["PYTHONUTF8"] = "1"

    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=creationflags,
            env=child_environment,
        )
        if os.name == "nt":
            process._workflow_job = WindowsProcessJob(process)
        if process.stdout is None:
            raise RuntimeError("Analyseprozess besitzt keinen lesbaren Ausgabekanal.")
        reader = threading.Thread(
            target=_read_process_lines,
            args=(process.stdout, lines),
            name="comskip-output-reader",
            daemon=True,
        )
        reader.start()

        output_finished = False
        while process.poll() is None or not output_finished or not lines.empty():
            while True:
                try:
                    raw_line = lines.get_nowait()
                except queue.Empty:
                    break
                if raw_line is None:
                    output_finished = True
                    continue
                line = decode_child_output(raw_line).rstrip("\r\n")
                phase_match = PHASE_RE.match(line)
                if phase_match:
                    phase = (int(phase_match.group(1)), int(phase_match.group(2)))
                    if phase == last_phase:
                        continue
                    last_phase = phase
                    print(f"[Phase {phase[0]}/{phase[1]}]")
                    continue
                if line.upper().startswith(("WARNUNG", "FEHLER")):
                    print(line)

            key = key_reader()
            if key == "b" and not stop_after_current:
                stop_after_current = True
                print("Batch-Stopp angefordert.")
                print("Aktueller Film wird noch fertig analysiert.")
                print("Danach Rückkehr ins Hauptmenü.")
            elif key == "x":
                aborted = True
                print("Sofortabbruch angefordert. Analyseprozessbaum wird beendet.")
                stop_process_tree(process)
                break
            time.sleep(0.05)

        returncode = process.wait()
        elapsed = format_elapsed(time.monotonic() - started)
        if aborted:
            print(colour(f"[{index}/{total}] ABBRUCH  {label} | {elapsed}", ANSI_RED))
        else:
            successful = returncode in (0, 1)
            status = "OK" if successful else f"FEHLER {returncode}"
            ansi = ANSI_BLUE if successful else ANSI_RED
            print(colour(f"[{index}/{total}] ENDE   {label} | {elapsed} | {status}", ansi))
        return AnalysisProcessResult(returncode, stop_after_current, aborted)

    except KeyboardInterrupt:
        aborted = True
        print("Strg+C erkannt. Analyseprozessbaum wird beendet.")
        stop_process_tree(process)
        elapsed = format_elapsed(time.monotonic() - started)
        print(colour(f"[{index}/{total}] ABBRUCH  {label} | {elapsed}", ANSI_RED))
        return AnalysisProcessResult(
            process.returncode if process is not None and process.returncode is not None else 130,
            False,
            True,
        )
    except Exception:
        stop_process_tree(process)
        raise
    finally:
        if process is not None:
            job = getattr(process, "_workflow_job", None)
            if job is not None:
                job.close()
        if process is not None and process.stdout is not None:
            try:
                process.stdout.close()
            except Exception:
                pass
        if reader is not None:
            reader.join(timeout=2)


def run_comskip_compact(comskip, video, downloads, idx, total):
    return run_analysis_command(
        [str(comskip), str(video)],
        downloads,
        idx,
        total,
        video.name,
    )


def avidemux_project_text(video, txt):
    total_frames, rate100, ads = parse_comskip_txt(txt)
    frame_us = int(round(100_000_000 / rate100))

    keeps, cursor = [], 0
    for a, b in ads:
        commercial_start = max(0, a - 1)
        commercial_end = b
        if commercial_start > cursor:
            keeps.append((cursor, commercial_start))
        cursor = max(cursor, commercial_end)
    if cursor < total_frames:
        keeps.append((cursor, total_frames))
    if not keeps:
        raise ValueError("Kein Filmsegment übrig.")

    vp = video.resolve().as_posix().replace('"', '\\"')
    out = [
        "#PY  <- Needed to identify #",
        "#--automatically built: Comskip -> Avidemux 2.8.1--",
        "adm = Avidemux()",
        "ed = Editor()",
        f'if not adm.loadVideo("{vp}"):',
        f'    raise("Cannot load {vp}")',
        "offset = ed.getTimeOffsetForSegment(0)",
        "if offset < 0:",
        '    raise("Cannot determine source PTS offset")',
        "sourceEnd = ed.getRefVideoDuration(0)",
        "if sourceEnd <= offset:",
        '    raise("Cannot determine source video end")',
        f"frameDuration = {frame_us}",
        "def framePts(frame):",
        "    return offset + frame * frameDuration",
        "def safeRestart(pts):",
        "    linearPts = pts - offset",
        "    if linearPts < 0:",
        '        raise("Invalid restart PTS before source start: " + str(pts))',
        "    k = ed.getPrevKFramePts(linearPts + 1)",
        "    if k < 0:",
        '        raise("No valid previous keyframe for restart PTS: " + str(pts))',
        "    if k > linearPts or ed.getPrevKFramePts(k + 1) != k:",
        '        raise("Invalid keyframe returned for restart PTS: " + str(pts))',
        "    return offset + k",
    ]

    for idx, (start, end) in enumerate(keeps, 1):
        end_expr = "sourceEnd" if end == total_frames else f"framePts({end})"
        out += [
            f"segmentStart{idx} = safeRestart(framePts({start}))",
            f"segmentEnd{idx} = {end_expr}",
        ]

    out += [
        "adm.clearSegments()",
        "totalDuration = 0",
    ]

    for idx, (start, end) in enumerate(keeps, 1):
        out += [
            f"# Filmsegment {idx}",
            f"segStart = segmentStart{idx}",
            f"segEnd = segmentEnd{idx}",
            "if segEnd > segStart:",
            "    segDuration = segEnd - segStart",
            "    adm.addSegment(0, segStart, segDuration)",
            "    totalDuration = totalDuration + segDuration",
        ]

    out += [
        "adm.setHDRConfig(1, 1, 1, 1, 0)",
        'adm.videoCodec("Copy")',
        "adm.audioClearTracks()",
        'adm.setSourceTrackLanguage(0,"und")',
        "if adm.audioTotalTracksCount() <= 0:",
        '    raise("Cannot add audio track 0, total tracks: " + str(adm.audioTotalTracksCount()))',
        "adm.audioAddTrack(0)",
        'adm.audioCodec(0, "copy")',
        "adm.audioSetDrc2(0, 0, 1, 0.001, 0.2, 1, 2, -12)",
        "adm.audioSetEq(0, 0, 0, 0, 0, 880, 5000)",
        "adm.audioSetChannelGains(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)",
        "adm.audioSetChannelDelays(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)",
        "adm.audioSetChannelRemap(0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8)",
        "adm.audioSetShift(0, 0, 0)",
        'adm.setContainer("MP4", "muxerType=0", "optimize=1", "forceAspectRatio=False", "aspectRatio=1", "displayWidth=1280", "rotation=0", "clockfreq=0")',
    ]
    return "\n".join(out) + "\n"


def avidemux_start_bat(target, load_video=False):
    variable = "VIDEO" if load_video else "PROJECT"
    argument = "--load" if load_video else "--run"
    template = r'''@echo off
setlocal EnableExtensions
set "__VARIABLE__=%~dp0__TARGET__"
set "AVIDEMUX="
for /f "delims=" %%I in ('where avidemux.exe 2^>nul') do if not defined AVIDEMUX set "AVIDEMUX=%%I"
if not defined AVIDEMUX if exist "%ProgramFiles%\Avidemux 2.8 VC++ 64bits\avidemux.exe" set "AVIDEMUX=%ProgramFiles%\Avidemux 2.8 VC++ 64bits\avidemux.exe"
if not defined AVIDEMUX if exist "%ProgramFiles%\Avidemux 2.8 - 64 bits\avidemux.exe" set "AVIDEMUX=%ProgramFiles%\Avidemux 2.8 - 64 bits\avidemux.exe"
if not defined AVIDEMUX if exist "%ProgramFiles%\Avidemux 2.8\avidemux.exe" set "AVIDEMUX=%ProgramFiles%\Avidemux 2.8\avidemux.exe"
if not defined AVIDEMUX if exist "%ProgramFiles%\Avidemux\avidemux.exe" set "AVIDEMUX=%ProgramFiles%\Avidemux\avidemux.exe"
if not defined AVIDEMUX (
 echo Avidemux wurde nicht gefunden.
 pause
 exit /b 1
)
start "" "%AVIDEMUX%" __ARGUMENT__ "%__VARIABLE__%"
'''
    return (
        template.replace("__VARIABLE__", variable)
        .replace("__TARGET__", target.name)
        .replace("__ARGUMENT__", argument)
    )


def remove_artifacts(video, suffixes):
    for suffix in suffixes:
        path = video.with_name(video.stem + suffix)
        if path.exists():
            path.unlink()


def write_crop_artifacts(video, txt):
    project = video.with_name(video.stem + CROP_SUFFIX)
    launcher = video.with_name(video.stem + CROP_START_SUFFIX)

    project_text = avidemux_project_text(video, txt)
    launcher_text = avidemux_start_bat(project)

    project.write_text(project_text, encoding="utf-8")
    launcher.write_text(launcher_text, encoding="utf-8-sig")

    remove_artifacts(
        video,
        (MANUAL_SUFFIX, MANUAL_START_SUFFIX, APPROVED_SUFFIX, START_SUFFIX),
    )

    return project, launcher


def write_manual_artifacts(video):
    marker = video.with_name(video.stem + MANUAL_SUFFIX)
    launcher = video.with_name(video.stem + MANUAL_START_SUFFIX)

    marker_text = "Comskip-Erkennung unbrauchbar. Film komplett manuell bearbeiten.\n"
    launcher_text = avidemux_start_bat(video, load_video=True)

    marker.write_text(marker_text, encoding="utf-8-sig")
    launcher.write_text(launcher_text, encoding="utf-8-sig")

    remove_artifacts(
        video,
        (CROP_SUFFIX, CROP_START_SUFFIX, APPROVED_SUFFIX, START_SUFFIX),
    )

    return marker, launcher


def decision_kind(video):
    crop = any(
        video.with_name(video.stem + suffix).exists()
        for suffix in (CROP_SUFFIX, APPROVED_SUFFIX)
    )
    manual = video.with_name(video.stem + MANUAL_SUFFIX).exists()

    if crop and manual:
        return "KONFLIKT"
    if crop:
        return "CROP"
    if manual:
        return "MANUELL"
    if is_complete_comskip_txt(video.with_suffix(".txt")):
        return "OFFEN"
    return "NICHT ANALYSIERT"


def decision_exists(video):
    return decision_kind(video) in ("CROP", "MANUELL", "KONFLIKT")


def ask_review_result():
    print("Bewertung:")
    print("  [C]rop    = final beschneiden (Werbung entfernt/nicht vorhanden)")
    print("  [M]anuell = komplett manuell bearbeiten")
    print("  [S]kip    = Film vorerst überspringen; Film bleibt offen")
    print("  [Q]uit    = Prüfung beenden; Film bleibt offen")
    while True:
        ans = input("Auswahl [C/M/S/Q]: ").strip().lower()
        if ans in (
            "c", "crop",
            "m", "manuell",
            "s", "skip", "ueberspringen", "überspringen",
            "q", "quit",
        ):
            return ans
        print("Bitte C, M, S oder Q eingeben.")


def ask_recheck_result(previous):
    print("Bewertung:")
    if previous in ("CROP", "MANUELL"):
        print(f"Bisherige Entscheidung: {previous}")
        print()
        print(f"  [Enter] = {previous} beibehalten und Dateien neu erzeugen")
    elif previous == "KONFLIKT":
        print("Bisherige Entscheidung: KONFLIKT")
        print("Bitte C oder M ausdrücklich wählen, um den Konflikt aufzulösen.")

    print("  [C]rop    = final beschneiden (Werbung entfernt/nicht vorhanden)")
    print("  [M]anuell = komplett manuell bearbeiten")
    if previous in ("CROP", "MANUELL"):
        print("  [Q]uit    = Entscheidung beibehalten und zurück")
    else:
        print("  [Q]uit    = ohne Entscheidung zurück zur Filmauswahl")

    while True:
        prompt = "Auswahl [Enter/C/M/Q]: " if previous in ("CROP", "MANUELL") else "Auswahl [C/M/Q]: "
        ans = input(prompt).strip().lower()
        if not ans and previous == "CROP":
            return "c"
        if not ans and previous == "MANUELL":
            return "m"
        if ans in ("c", "crop", "m", "manuell", "q", "quit"):
            return ans
        if previous in ("CROP", "MANUELL"):
            print("Bitte Enter, C, M oder Q eingeben.")
        else:
            print("Bitte C, M oder Q eingeben.")


def analyse_video(comskip, video, downloads, idx, total, force=False):
    txt = video.with_suffix(".txt")
    if not force and is_complete_comskip_txt(txt):
        print(f"[Analyse {idx}/{total}] vorhanden: {video.name}")
        return True

    output_snapshot = None
    reanalysis_backup = None
    staged_reanalysis_files = []
    if force:
        try:
            reanalysis_backup, staged_reanalysis_files = stage_reanalysis_artifacts(video)
        except Exception as exc:
            print(f"FEHLER beim Sichern der bisherigen Dateien für: {video.name}")
            print(f"{type(exc).__name__}: {exc}")
            return False
        if reanalysis_backup is not None:
            print("Bisherige Analyse und Entscheidung gesichert in:")
            print(reanalysis_backup)
    else:
        output_snapshot = snapshot_analysis_outputs(video)
    try:
        process_result = run_comskip_compact(comskip, video, downloads, idx, total)
    except Exception as exc:
        if force:
            restore_staged_reanalysis_artifacts(reanalysis_backup, staged_reanalysis_files)
        print(f"FEHLER bei: {video.name}")
        print(f"{type(exc).__name__}: {exc}")
        print("Der Stapel wird mit dem nächsten Film fortgesetzt.")
        return False

    if process_result.aborted:
        if force:
            restore_staged_reanalysis_artifacts(reanalysis_backup, staged_reanalysis_files)
        else:
            restore_analysis_outputs(output_snapshot)
        print(f"Analyse abgebrochen: {video.name}")
        print("Neue unvollständige Ergebnisse wurden entfernt; vorhandene Benutzerdateien sind wiederhergestellt.")
        print("Rückkehr ins Hauptmenü.")
        raise ReturnToMainMenu

    returncode = process_result.returncode
    completed = False
    if is_complete_comskip_txt(txt):
        if returncode not in (0, 1):
            print(
                f"WARNUNG: Returncode {returncode}, aber vollständige Comskip-TXT vorhanden; "
                "Analyse wird akzeptiert."
            )
        completed = True
    else:
        if returncode in (0, 1):
            print(f"WARNUNG: Keine vollständige Comskip-TXT erzeugt für: {video.name}")
        else:
            print(f"WARNUNG: Comskip-Fehler bei {video.name} | Returncode {returncode}")

    if force and not completed:
        restore_staged_reanalysis_artifacts(reanalysis_backup, staged_reanalysis_files)
        print("Neuanalyse nicht vollständig; bisherige Analyse und Entscheidung wurden wiederhergestellt.")
    elif force:
        print("Neuanalyse vollständig. Dieser Film ist jetzt wieder OFFEN und muss erneut geprüft werden.")
        if reanalysis_backup is not None:
            print("Die vorherige Fassung bleibt wiederherstellbar unter:")
            print(reanalysis_backup)

    if process_result.stop_after_current:
        print("Batch nach aktuellem Film beendet. Rückkehr ins Hauptmenü.")
        raise ReturnToMainMenu
    return completed


def workflow_status(videos):
    analysed = 0
    decided = 0
    open_review = 0

    for video in videos:
        txt = video.with_suffix(".txt")
        complete = is_complete_comskip_txt(txt)
        decision = decision_exists(video)

        if complete:
            analysed += 1
        if decision:
            decided += 1
        if complete and not decision:
            open_review += 1

    return analysed, decided, open_review


def ask_start_mode(videos, working_directory):
    analysed, decided, open_review = workflow_status(videos)

    print()
    print("Status:")
    print(f"  Arbeitsordner        : {working_directory}")
    print(f"  MP4-Dateien gefunden : {len(videos)}")
    print(f"  Comskip analysiert   : {analysed}")
    print(f"  Bereits entschieden  : {decided}")
    print(f"  Noch zu prüfen       : {open_review}")
    print()
    print("Was möchtest du tun?")
    print("  [A] Analysieren und danach offene Filme prüfen")
    print("  [N] Nur analysieren")
    print("  [P] Nur offene Filme prüfen / Prüfung fortsetzen")
    print("  [E] Film auswählen / erneut prüfen")
    print("  [R] Einen Film gezielt neu analysieren")
    print("  [V] Verzeichnis für diesen Durchlauf wählen")
    print("  [Q] Beenden")

    while True:
        ans = input("Auswahl [A/N/P/E/R/V/Q]: ").strip().lower()
        if ans in ("a", "analyse", "analysieren"):
            return "a"
        if ans in ("n", "nur", "nur analysieren"):
            return "n"
        if ans in ("p", "pruefen", "prüfen", "fortsetzen"):
            return "p"
        if ans in ("e", "erneut", "auswaehlen", "auswählen"):
            return "e"
        if ans in ("r", "reanalyse", "neu analysieren", "neuanalyse"):
            return "r"
        if ans in ("v", "verzeichnis", "ordner"):
            return "v"
        if ans in ("q", "quit", "beenden"):
            return "q"
        print("Bitte A, N, P, E, R, V oder Q eingeben.")


def run_reanalysis_menu(comskip, downloads):
    while True:
        videos = find_videos(downloads)
        print()
        print("Film gezielt neu analysieren")
        print()

        if not videos:
            print("Keine MP4-Dateien gefunden.")
            return

        for idx, video in enumerate(videos, 1):
            status = decision_kind(video)
            station = " | WeDo Movies" if "wedo-movies" in video.name else ""
            print(f"{idx:2d}  [{status:<17}] {video.name}{station}")
        print()
        print(" 0  Zurück")

        choice = input("Nummer: ").strip()
        if choice == "0":
            return
        if not choice.isdigit():
            print("Bitte eine gültige Nummer eingeben.")
            continue

        selected = int(choice)
        if selected < 1 or selected > len(videos):
            print("Bitte eine gültige Nummer eingeben.")
            continue

        video = videos[selected - 1]
        print()
        print("Ausgewählt:", video.name)
        print("Nur dieser Film wird neu analysiert.")
        print("Seine bisherige Analyse und CROP-/MANUELL-Entscheidung werden vorher gesichert.")
        answer = input("Neuanalyse starten [J/N]: ").strip().lower()
        if answer not in ("j", "ja", "y", "yes"):
            print("Neuanalyse nicht gestartet.")
            continue

        completed = analyse_video(comskip, video, downloads, 1, 1, force=True)
        if completed:
            print("Die neue Analyse kann anschließend mit [P] geprüft werden.")
        input("Enter für das Hauptmenü ...")
        return


def report_txt_change(txt, txt_before):
    try:
        txt_after = txt.read_bytes()
        if txt_after != txt_before:
            print("Comskip-TXT: gespeicherte Änderungen erkannt.")
            return True
        else:
            print("Comskip-TXT: unverändert.")
            return False
    except Exception as exc:
        print(f"WARNUNG: Änderung der Comskip-TXT konnte nicht geprüft werden: {exc}")
        return None


def review_selected_video(video, comskip, gui, downloads):
    previous = decision_kind(video)
    txt = video.with_suffix(".txt")

    if previous == "KONFLIKT":
        print()
        print("WARNUNG: Für diesen Film sind CROP- und MANUELL-Marker vorhanden.")
        print("Es wird keine Entscheidung automatisch übernommen.")

    if not is_complete_comskip_txt(txt):
        print(f"Noch keine vollständige Comskip-TXT vorhanden: {video.name}")
        if not analyse_video(comskip, video, downloads, 1, 1):
            print("Der Film konnte nicht vollständig analysiert werden.")
            return
        if previous == "NICHT ANALYSIERT":
            previous = "OFFEN"

    try:
        txt_before = txt.read_bytes()
        run_comskip_gui(gui, txt, downloads)
    except Exception as exc:
        print(f"FEHLER beim Start von ComskipGUI für: {video.name}")
        print(f"{type(exc).__name__}: {exc}")
        return

    txt_changed = report_txt_change(txt, txt_before)
    ans = ask_recheck_result(previous)

    if ans in ("q", "quit"):
        if txt_changed and previous == "CROP":
            print("TXT geändert: CROP bleibt bestehen; Dateien werden neu erzeugt.")
            ans = "c"
        elif txt_changed and previous == "MANUELL":
            print("TXT geändert: MANUELL bleibt bestehen; Dateien werden neu erzeugt.")
            ans = "m"
        else:
            print("Ohne neue Entscheidung zurück zur Filmauswahl.")
            return

    if ans in ("m", "manuell"):
        try:
            marker, launcher = write_manual_artifacts(video)
            print("Erzeugt:", marker.name)
            print("Erzeugt:", launcher.name)
        except Exception as exc:
            print(f"FEHLER beim Erzeugen der MANUELL-Artefakte für: {video.name}")
            print(f"{type(exc).__name__}: {exc}")
        return

    try:
        project, launcher = write_crop_artifacts(video, txt)
        print("Erzeugt:", project.name)
        print("Erzeugt:", launcher.name)
    except Exception as exc:
        print(f"FEHLER beim Erzeugen des Crop-Avidemux-Projekts für: {video.name}")
        print(f"{type(exc).__name__}: {exc}")


def run_recheck_menu(comskip, gui, downloads):
    while True:
        videos = find_videos(downloads)
        print()
        print("Film auswählen / erneut prüfen")
        print()

        if not videos:
            print("Keine MP4-Dateien gefunden.")
            print(" 0  Zurück")
        else:
            for idx, video in enumerate(videos, 1):
                status = decision_kind(video)
                print(f"{idx:2d}  [{status:<17}] {video.name}")
            print()
            print(" 0  Zurück")

        choice = input("Nummer: ").strip()
        if choice == "0":
            return
        if not choice.isdigit():
            print("Bitte eine gültige Nummer eingeben.")
            continue

        selected = int(choice)
        if selected < 1 or selected > len(videos):
            print("Bitte eine gültige Nummer eingeben.")
            continue

        video = videos[selected - 1]
        print()
        print("Ausgewählt:", video.name)
        review_selected_video(video, comskip, gui, downloads)


def run_session():
    global _SESSION_DIRECTORY
    workflow_dir = Path(__file__).resolve().parent
    comskip_dir = workflow_dir.parent
    comskip_core = comskip_dir / "comskip.exe"
    comskip_final = comskip_dir / "comskip-final.exe"
    comskip = comskip_final if comskip_final.exists() else comskip_core
    gui = comskip_dir / "ComskipGUI.exe"
    if _SESSION_DIRECTORY is None:
        _SESSION_DIRECTORY = downloads_folder()
    downloads = _SESSION_DIRECTORY

    print("=" * 72)
    print("COMSKIP -> PRUEFEN -> AVIDEMUX")
    print("=" * 72)
    print("Workflow-Ordner:", workflow_dir)
    print("Comskip-Ordner :", comskip_dir)
    print("Analyse        :", comskip.name)
    print("Arbeitsordner  :", downloads)
    print("Skript         :", Path(__file__).resolve())
    print("Build          :", BUILD_ID)
    print("Ausgabe        : KOMPAKT (Start, Phasen, Ende)")

    if not comskip.exists() or not gui.exists():
        print("FEHLER: Comskip-Analyse oder ComskipGUI.exe wurde eine Ebene höher nicht gefunden.")
        input("Enter zum Beenden ...")
        return 2

    while True:
        videos = find_videos(downloads)
        mode = ask_start_mode(videos, downloads)
        if mode == "q":
            print("Beendet.")
            return 0
        if mode == "v":
            downloads = choose_session_folder(downloads)
            _SESSION_DIRECTORY = downloads
            continue
        if mode == "e":
            run_recheck_menu(comskip, gui, downloads)
            continue
        if mode == "r":
            run_reanalysis_menu(comskip, downloads)
            continue
        break

    if mode in ("a", "n"):
        if not videos:
            print("Keine MP4-Dateien im gewählten Arbeitsordner gefunden.")
            return 0
        print("Steuerung: [B] nach aktuellem Film stoppen | [X] sofort abbrechen")
        for idx, video in enumerate(videos, 1):
            analyse_video(comskip, video, downloads, idx, len(videos))

        print("Analysephase fertig.")

        if mode == "n":
            analysed, decided, open_review = workflow_status(videos)
            print(
                f"Stand: {analysed} analysiert, {decided} bereits entschieden, "
                f"{open_review} noch zu prüfen."
            )
            print("Nur-Analyse-Modus beendet. Zum Fortsetzen später [P] wählen.")
            input("Enter zum Beenden ...")
            return 0

    review = []
    for video in videos:
        txt = video.with_suffix(".txt")
        if is_complete_comskip_txt(txt) and not decision_exists(video):
            review.append((video, txt))

    if not review:
        print("Keine offenen Filme zur Prüfung vorhanden.")
        input("Enter zum Beenden ...")
        return 0

    print(f"Prüfphase: {len(review)} Film(e) offen.")
    for idx, (video, txt) in enumerate(review, 1):
        print(f"[Prüfung {idx}/{len(review)}] {video.name}")
        while True:
            txt_before = txt.read_bytes()
            try:
                run_comskip_gui(gui, txt, downloads)
            except Exception as exc:
                print(f"FEHLER beim Start von ComskipGUI für: {video.name}")
                print(f"{type(exc).__name__}: {exc}")
                print("Der Stapel wird mit dem nächsten Film fortgesetzt.")
                break

            report_txt_change(txt, txt_before)

            ans = ask_review_result()

            if ans in ("q", "quit"):
                remaining = len(review) - idx + 1
                print()
                print("Prüfung unterbrochen.")
                print("Der aktuelle Film bleibt ohne C/M-Entscheidung offen.")
                print(f"Noch offen in dieser Liste: {remaining}")
                print("Beim nächsten Start einfach [P] wählen.")
                input("Enter zum Beenden ...")
                return 0

            if ans in ("s", "skip", "ueberspringen", "überspringen"):
                print("Film vorerst übersprungen; er bleibt zur Prüfung offen.")
                print("Der Stapel wird mit dem nächsten Film fortgesetzt.")
                break

            if ans in ("m", "manuell"):
                try:
                    marker, launcher = write_manual_artifacts(video)
                    print("Erzeugt:", marker.name)
                    print("Erzeugt:", launcher.name)
                except Exception as exc:
                    print(f"FEHLER beim Erzeugen der MANUELL-Artefakte für: {video.name}")
                    print(f"{type(exc).__name__}: {exc}")
                break

            try:
                p, b = write_crop_artifacts(video, txt)
                print("Erzeugt:", p.name)
                print("Erzeugt:", b.name)
            except Exception as exc:
                print(f"FEHLER beim Erzeugen des Crop-Avidemux-Projekts für: {video.name}")
                print(f"{type(exc).__name__}: {exc}")
            break

    analysed, decided, open_review = workflow_status(videos)
    print("Fertig.")
    print(
        f"Stand: {analysed} analysiert, {decided} bereits entschieden, "
        f"{open_review} noch zu prüfen."
    )
    input("Enter zum Beenden ...")
    return 0


def main():
    configure_console()
    while True:
        try:
            return run_session()
        except ReturnToMainMenu:
            print()
            continue
        except KeyboardInterrupt:
            print()
            print("Strg+C erkannt. Kein Analyseprozess ist mehr aktiv.")
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
