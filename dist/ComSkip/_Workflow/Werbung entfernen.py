# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None

BUILD_ID = "2026-10-02-COMSKIP-V4.3-MULTI-STSD-CTTS"
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

PAL_SD_WIDTHS = (704, 720)
PAL_SD_HEIGHT = 576
ASPECT_SAMPLE_SECONDS = 3.0
ASPECT_SAMPLE_MARGIN_SECONDS = 2.0
ASPECT_SAMPLE_FRACTIONS = (0.10, 0.26, 0.42, 0.58, 0.74, 0.90)
MAX_ASPECT_SAMPLES = 12
MIN_VALID_ASPECT_SAMPLES = 3

SHOWINFO_SAR_RE = re.compile(r"\bsar:(\d+)/(\d+)\b")
SHOWINFO_SIZE_RE = re.compile(r"\bs:(\d+)x(\d+)\b")


class ReturnToMainMenu(Exception):
    """Internal control flow after a requested batch/analysis stop."""


@dataclass(frozen=True)
class AnalysisProcessResult:
    returncode: int
    stop_after_current: bool = False
    aborted: bool = False


@dataclass(frozen=True)
class AspectDecision:
    force: bool = False
    aspect_ratio: int = 1
    display_width: int = 1280
    expected_dar: str = ""
    description: str = "Nicht-PAL-SD; bisherige Containerkonfiguration bleibt aktiv."
    warning: str = ""
    samples: tuple = ()


@dataclass(frozen=True)
class Mp4AspectMap:
    is_mp4: bool = False
    stsd_count: int = 0
    samples: tuple = ()
    error: str = ""


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


def display_video_name(video_name):
    """Return the real file name without normalising any characters."""
    return Path(video_name).name


def replace_status_line(text):
    """Replace one live terminal line; keep full lines when output is redirected."""
    if not getattr(sys.stdout, "isatty", lambda: False)():
        print(text)
        return False

    width = max(20, shutil.get_terminal_size((120, 24)).columns - 1)
    visible = text if len(text) <= width else text[: max(1, width - 1)] + "…"
    print(f"\r\x1b[2K{visible}", end="", flush=True)
    return True


def clear_status_line(active):
    if active:
        print("\r\x1b[2K", end="", flush=True)


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


def build_keep_segments(total_frames, ads):
    keeps, cursor = [], 0
    for a, b in ads:
        commercial_start = max(0, a - 1)
        commercial_end = b
        if commercial_start > cursor:
            keeps.append((cursor, commercial_start))
        cursor = max(cursor, commercial_end)
    if cursor < total_frames:
        keeps.append((cursor, total_frames))
    return keeps


def find_media_executable(name):
    portable = Path(__file__).resolve().parent.parent / name
    if portable.is_file():
        return portable

    found = shutil.which(name)
    if found:
        return Path(found)

    stem = Path(name).stem
    found = shutil.which(stem)
    return Path(found) if found else None


def probe_video_geometry(video, ffprobe):
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [
                str(ffprobe),
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(video),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None

    try:
        payload = json.loads(completed.stdout)
        stream = payload.get("streams", [])[0]
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
    except (ValueError, TypeError, IndexError, AttributeError):
        return None

    if width <= 0 or height <= 0:
        return None
    return width, height


def get_keep_sample_positions(keeps, rate100):
    if rate100 <= 0:
        return []

    seconds_per_frame = 100.0 / rate100
    safe_segments = []
    for start_frame, end_frame in keeps:
        start = start_frame * seconds_per_frame
        end = end_frame * seconds_per_frame
        first = start + ASPECT_SAMPLE_MARGIN_SECONDS
        last = end - ASPECT_SAMPLE_MARGIN_SECONDS - ASPECT_SAMPLE_SECONDS
        if last < first:
            continue
        safe_segments.append((start, end, first, last))

    if not safe_segments:
        return []

    if len(safe_segments) > MAX_ASPECT_SAMPLES:
        selected = sorted(
            safe_segments,
            key=lambda segment: segment[1] - segment[0],
            reverse=True,
        )[:MAX_ASPECT_SAMPLES]
    else:
        selected = safe_segments

    positions = {
        round((first + last) / 2.0, 3)
        for _start, _end, first, last in selected
    }

    if len(positions) < MAX_ASPECT_SAMPLES:
        total_duration = sum(end - start for start, end, _first, _last in safe_segments)
        for fraction in ASPECT_SAMPLE_FRACTIONS:
            remaining = total_duration * fraction
            chosen = None
            for start, end, first, last in safe_segments:
                duration = end - start
                if remaining <= duration:
                    centre = start + remaining
                    chosen = min(max(centre - ASPECT_SAMPLE_SECONDS / 2.0, first), last)
                    break
                remaining -= duration
            if chosen is None:
                chosen = safe_segments[-1][3]
            positions.add(round(chosen, 3))
            if len(positions) >= MAX_ASPECT_SAMPLES:
                break

    return sorted(positions)


def _mp4_boxes(data, start=0, end=None):
    end = len(data) if end is None else end
    offset = start
    while offset + 8 <= end:
        size = struct.unpack_from(">I", data, offset)[0]
        box_type = data[offset + 4:offset + 8]
        header_size = 8
        if size == 1:
            if offset + 16 > end:
                raise ValueError("Unvollstaendiger 64-Bit-MP4-Boxheader")
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - offset
        if box_type == b"uuid":
            header_size += 16
        if size < header_size or offset + size > end:
            raise ValueError(f"Ungueltige MP4-Box {box_type!r}")
        yield box_type, offset, offset + header_size, offset + size
        offset += size


def _mp4_child(data, start, end, wanted):
    for box_type, _box_start, payload_start, box_end in _mp4_boxes(data, start, end):
        if box_type == wanted:
            return payload_start, box_end
    return None


def _read_mp4_moov(video):
    with video.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        file_size = stream.tell()
        stream.seek(0)
        offset = 0
        found_ftyp = False
        while offset + 8 <= file_size:
            stream.seek(offset)
            header = stream.read(16)
            if len(header) < 8:
                break
            size = struct.unpack_from(">I", header, 0)[0]
            box_type = header[4:8]
            header_size = 8
            if size == 1:
                if len(header) < 16:
                    raise ValueError("Unvollstaendiger 64-Bit-MP4-Boxheader")
                size = struct.unpack_from(">Q", header, 8)[0]
                header_size = 16
            elif size == 0:
                size = file_size - offset
            if box_type == b"uuid":
                header_size += 16
            if size < header_size or offset + size > file_size:
                raise ValueError(f"Ungueltige Top-Level-MP4-Box {box_type!r}")
            if box_type == b"ftyp":
                found_ftyp = True
            if box_type == b"moov":
                if size - header_size > 256 * 1024 * 1024:
                    raise ValueError("MP4-moov-Box ist unerwartet gross")
                stream.seek(offset + header_size)
                return found_ftyp, stream.read(size - header_size)
            offset += size
    return found_ftyp, None


class _BitReader:
    def __init__(self, data):
        self.data = data
        self.bit = 0

    def read_bits(self, count):
        if count < 0 or self.bit + count > len(self.data) * 8:
            raise ValueError("H.264-SPS ist unvollstaendig")
        value = 0
        for _ in range(count):
            value = (value << 1) | ((self.data[self.bit // 8] >> (7 - self.bit % 8)) & 1)
            self.bit += 1
        return value

    def read_ue(self):
        zeros = 0
        while self.read_bits(1) == 0:
            zeros += 1
            if zeros > 31:
                raise ValueError("Ungueltiger Exp-Golomb-Wert in H.264-SPS")
        return (1 << zeros) - 1 + (self.read_bits(zeros) if zeros else 0)

    def read_se(self):
        value = self.read_ue()
        return (value + 1) // 2 if value & 1 else -(value // 2)


def _skip_h264_scaling_list(reader, size):
    last_scale = 8
    next_scale = 8
    for _ in range(size):
        if next_scale:
            next_scale = (last_scale + reader.read_se() + 256) % 256
        if next_scale:
            last_scale = next_scale


def _h264_sps_sar(sps):
    if not sps:
        return None
    rbsp = bytearray()
    zero_count = 0
    for value in sps[1:]:  # NAL-Header auslassen und Emulation-Prevention entfernen.
        if zero_count >= 2 and value == 3:
            zero_count = 0
            continue
        rbsp.append(value)
        zero_count = zero_count + 1 if value == 0 else 0

    reader = _BitReader(bytes(rbsp))
    profile_idc = reader.read_bits(8)
    reader.read_bits(8)  # constraint flags + reserved_zero_2bits
    reader.read_bits(8)  # level_idc
    reader.read_ue()     # seq_parameter_set_id

    if profile_idc in {44, 83, 86, 100, 110, 118, 122, 128, 134, 135, 138, 139, 144, 244}:
        chroma_format_idc = reader.read_ue()
        if chroma_format_idc == 3:
            reader.read_bits(1)
        reader.read_ue()
        reader.read_ue()
        reader.read_bits(1)
        if reader.read_bits(1):
            scaling_count = 8 if chroma_format_idc != 3 else 12
            for index in range(scaling_count):
                if reader.read_bits(1):
                    _skip_h264_scaling_list(reader, 16 if index < 6 else 64)

    reader.read_ue()  # log2_max_frame_num_minus4
    pic_order_cnt_type = reader.read_ue()
    if pic_order_cnt_type == 0:
        reader.read_ue()
    elif pic_order_cnt_type == 1:
        reader.read_bits(1)
        reader.read_se()
        reader.read_se()
        for _ in range(reader.read_ue()):
            reader.read_se()
    reader.read_ue()  # max_num_ref_frames
    reader.read_bits(1)
    reader.read_ue()  # pic_width_in_mbs_minus1
    reader.read_ue()  # pic_height_in_map_units_minus1
    frame_mbs_only = reader.read_bits(1)
    if not frame_mbs_only:
        reader.read_bits(1)
    reader.read_bits(1)
    if reader.read_bits(1):
        reader.read_ue()
        reader.read_ue()
        reader.read_ue()
        reader.read_ue()
    if not reader.read_bits(1) or not reader.read_bits(1):
        return None

    aspect_ratio_idc = reader.read_bits(8)
    if aspect_ratio_idc == 255:
        sar_num = reader.read_bits(16)
        sar_den = reader.read_bits(16)
    else:
        known = {
            1: (1, 1), 2: (12, 11), 3: (10, 11), 4: (16, 11),
            5: (40, 33), 6: (24, 11), 7: (20, 11), 8: (32, 11),
            9: (80, 33), 10: (18, 11), 11: (15, 11), 12: (64, 33),
            13: (160, 99), 14: (4, 3), 15: (3, 2), 16: (2, 1),
        }
        if aspect_ratio_idc not in known:
            return None
        sar_num, sar_den = known[aspect_ratio_idc]
    if sar_num <= 0 or sar_den <= 0:
        return None
    ratio = Fraction(sar_num, sar_den)
    return ratio.numerator, ratio.denominator


def _avcc_sar(avcc):
    if len(avcc) < 7:
        return None
    count = avcc[5] & 0x1F
    offset = 6
    ratios = set()
    for _ in range(count):
        if offset + 2 > len(avcc):
            raise ValueError("Unvollstaendige SPS-Laenge in avcC")
        size = struct.unpack_from(">H", avcc, offset)[0]
        offset += 2
        if offset + size > len(avcc):
            raise ValueError("Unvollstaendige SPS in avcC")
        ratio = _h264_sps_sar(avcc[offset:offset + size])
        offset += size
        if ratio:
            ratios.add(ratio)
    return next(iter(ratios)) if len(ratios) == 1 else None


def _parse_stsd_entries(data, stsd):
    start, end = stsd
    if start + 8 > end:
        raise ValueError("Unvollstaendige stsd-Box")
    entry_count = struct.unpack_from(">I", data, start + 4)[0]
    offset = start + 8
    entries = []
    for index in range(1, entry_count + 1):
        if offset + 8 > end:
            raise ValueError("Unvollstaendiger stsd-Eintrag")
        size = struct.unpack_from(">I", data, offset)[0]
        codec = data[offset + 4:offset + 8]
        entry_end = offset + size
        if size < 86 or entry_end > end:
            raise ValueError("Ungueltiger visueller stsd-Eintrag")
        width, height = struct.unpack_from(">HH", data, offset + 32)
        avcc = _mp4_child(data, offset + 86, entry_end, b"avcC")
        sar = None
        if codec in (b"avc1", b"avc3") and avcc:
            sar = _avcc_sar(data[avcc[0]:avcc[1]])
        entries.append({
            "index": index,
            "codec": codec.decode("latin-1", errors="replace"),
            "width": width,
            "height": height,
            "sar": sar,
        })
        offset = entry_end
    return entries


def _parse_fullbox_table(data, box, item_size, fmt):
    start, end = box
    if start + 8 > end:
        raise ValueError("Unvollstaendige MP4-Tabelle")
    count = struct.unpack_from(">I", data, start + 4)[0]
    offset = start + 8
    if offset + count * item_size > end:
        raise ValueError("Abgeschnittene MP4-Tabelle")
    return [struct.unpack_from(fmt, data, offset + index * item_size) for index in range(count)]


def _parse_ctts_entries(data, box):
    if box is None:
        return []
    start, end = box
    if start + 8 > end:
        raise ValueError("Unvollstaendige ctts-Box")
    version = data[start]
    if version not in (0, 1):
        raise ValueError(f"Nicht unterstuetzte ctts-Version {version}")
    count = struct.unpack_from(">I", data, start + 4)[0]
    offset = start + 8
    entries = []
    offset_format = ">i" if version == 1 else ">I"
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError("Abgeschnittene ctts-Box")
        sample_count = struct.unpack_from(">I", data, offset)[0]
        composition_offset = struct.unpack_from(offset_format, data, offset + 4)[0]
        entries.append((sample_count, composition_offset))
        offset += 8
    return entries


def _parse_mp4_timescale(data, box):
    start, end = box
    if start + 4 > end:
        raise ValueError("Unvollstaendige MP4-Zeitbasis")
    version = data[start]
    offset = start + (20 if version == 1 else 12)
    if offset + 4 > end:
        raise ValueError("Unvollstaendige MP4-Zeitbasis")
    return struct.unpack_from(">I", data, offset)[0]


def _parse_mp4_edits(data, box):
    if box is None:
        return []
    start, end = box
    if start + 8 > end:
        raise ValueError("Unvollstaendige elst-Box")
    version = data[start]
    count = struct.unpack_from(">I", data, start + 4)[0]
    offset = start + 8
    edits = []
    for _ in range(count):
        if version == 1:
            if offset + 20 > end:
                raise ValueError("Abgeschnittene elst-Box")
            duration = struct.unpack_from(">Q", data, offset)[0]
            media_time = struct.unpack_from(">q", data, offset + 8)[0]
            rate_integer, rate_fraction = struct.unpack_from(">hh", data, offset + 16)
            offset += 20
        else:
            if offset + 12 > end:
                raise ValueError("Abgeschnittene elst-Box")
            duration = struct.unpack_from(">I", data, offset)[0]
            media_time = struct.unpack_from(">i", data, offset + 4)[0]
            rate_integer, rate_fraction = struct.unpack_from(">hh", data, offset + 8)
            offset += 12
        if rate_integer != 1 or rate_fraction != 0:
            raise ValueError("Nicht unterstuetzte MP4-Edit-Abspielrate")
        edits.append((duration, media_time))
    return edits


def _movie_position_to_media_time(position, movie_scale, track_scale, edits):
    movie_time = Fraction(str(position)) * movie_scale
    if not edits:
        return Fraction(str(position)) * track_scale
    cursor = Fraction(0)
    for duration, media_time in edits:
        segment_end = cursor + duration
        if cursor <= movie_time < segment_end:
            if media_time < 0:
                return None
            return Fraction(media_time) + (movie_time - cursor) * track_scale / movie_scale
        cursor = segment_end
    return None


def _media_time_to_sample(media_time, stts_entries):
    if media_time is None or media_time < 0:
        return None
    elapsed = Fraction(0)
    sample_index = 0
    for count, delta in stts_entries:
        if count <= 0 or delta <= 0:
            raise ValueError("Ungueltiger stts-Eintrag")
        run_end = elapsed + count * delta
        if media_time < run_end:
            return sample_index + int((media_time - elapsed) // delta)
        elapsed = run_end
        sample_index += count
    return None


def _presentation_samples_for_media_times(media_times, stts_entries, ctts_entries):
    """Map presentation times to decode-order samples, including B-frame offsets."""
    if not ctts_entries:
        return [_media_time_to_sample(media_time, stts_entries) for media_time in media_times]

    stts_sample_count = sum(count for count, _delta in stts_entries)
    ctts_sample_count = sum(count for count, _offset in ctts_entries)
    if stts_sample_count != ctts_sample_count:
        raise ValueError("stts/ctts enthalten unterschiedliche Samplezahlen")

    def composition_offsets():
        for count, composition_offset in ctts_entries:
            if count <= 0:
                raise ValueError("Ungueltiger ctts-Eintrag")
            for _ in range(count):
                yield composition_offset

    targets = [media_time if media_time is not None and media_time >= 0 else None for media_time in media_times]
    best_samples = [None] * len(targets)
    best_times = [None] * len(targets)
    offsets = composition_offsets()
    decode_time = 0
    sample_index = 0
    for count, delta in stts_entries:
        if count <= 0 or delta <= 0:
            raise ValueError("Ungueltiger stts-Eintrag")
        for _ in range(count):
            presentation_time = decode_time + next(offsets)
            for target_index, target in enumerate(targets):
                if target is None or presentation_time > target:
                    continue
                previous = best_times[target_index]
                if previous is None or presentation_time >= previous:
                    best_times[target_index] = presentation_time
                    best_samples[target_index] = sample_index
            decode_time += delta
            sample_index += 1
    return best_samples


def _sample_description_for_sample(sample_index, stsc_entries, chunk_count):
    if sample_index is None or sample_index < 0:
        return None
    sample_cursor = 0
    for index, (first_chunk, samples_per_chunk, description_index) in enumerate(stsc_entries):
        next_first = stsc_entries[index + 1][0] if index + 1 < len(stsc_entries) else chunk_count + 1
        run_chunks = next_first - first_chunk
        if first_chunk < 1 or samples_per_chunk < 1 or description_index < 1 or run_chunks < 1:
            raise ValueError("Ungueltiger stsc-Eintrag")
        run_samples = run_chunks * samples_per_chunk
        if sample_index < sample_cursor + run_samples:
            return description_index
        sample_cursor += run_samples
    return None


def probe_mp4_active_sps_samples(video, positions):
    try:
        found_ftyp, moov = _read_mp4_moov(video)
    except (OSError, ValueError) as exc:
        return Mp4AspectMap(is_mp4=video.suffix.lower() == ".mp4", error=str(exc))
    if not found_ftyp:
        return Mp4AspectMap()
    if moov is None:
        return Mp4AspectMap(is_mp4=True, error="MP4 enthaelt keine lesbare moov-Box")

    try:
        mvhd = _mp4_child(moov, 0, len(moov), b"mvhd")
        if mvhd is None:
            raise ValueError("MP4 enthaelt keine mvhd-Box")
        movie_scale = _parse_mp4_timescale(moov, mvhd)
        video_trak = None
        for box_type, _box_start, payload_start, box_end in _mp4_boxes(moov):
            if box_type != b"trak":
                continue
            mdia = _mp4_child(moov, payload_start, box_end, b"mdia")
            if mdia is None:
                continue
            hdlr = _mp4_child(moov, mdia[0], mdia[1], b"hdlr")
            if hdlr and hdlr[0] + 12 <= hdlr[1] and moov[hdlr[0] + 8:hdlr[0] + 12] == b"vide":
                video_trak = (payload_start, box_end, mdia)
                break
        if video_trak is None:
            raise ValueError("MP4 enthaelt keinen Videotrack")

        trak_start, trak_end, mdia = video_trak
        mdhd = _mp4_child(moov, mdia[0], mdia[1], b"mdhd")
        minf = _mp4_child(moov, mdia[0], mdia[1], b"minf")
        stbl = _mp4_child(moov, minf[0], minf[1], b"stbl") if minf else None
        if mdhd is None or stbl is None:
            raise ValueError("Videotrack enthaelt keine vollstaendige Zeit-/Sampletabelle")
        track_scale = _parse_mp4_timescale(moov, mdhd)

        stsd = _mp4_child(moov, stbl[0], stbl[1], b"stsd")
        stsc = _mp4_child(moov, stbl[0], stbl[1], b"stsc")
        stts = _mp4_child(moov, stbl[0], stbl[1], b"stts")
        ctts = _mp4_child(moov, stbl[0], stbl[1], b"ctts")
        stco = _mp4_child(moov, stbl[0], stbl[1], b"stco")
        co64 = _mp4_child(moov, stbl[0], stbl[1], b"co64")
        if None in (stsd, stsc, stts) or (stco is None and co64 is None):
            raise ValueError("Videotrack enthaelt keine vollstaendige stsd/stsc/stts/stco-Tabelle")

        descriptions = _parse_stsd_entries(moov, stsd)
        stsc_entries = _parse_fullbox_table(moov, stsc, 12, ">III")
        stts_entries = _parse_fullbox_table(moov, stts, 8, ">II")
        ctts_entries = _parse_ctts_entries(moov, ctts)
        chunk_box = stco if stco is not None else co64
        chunk_start, chunk_end = chunk_box
        if chunk_start + 8 > chunk_end:
            raise ValueError("Unvollstaendige Chunk-Tabelle")
        chunk_count = struct.unpack_from(">I", moov, chunk_start + 4)[0]

        edts = _mp4_child(moov, trak_start, trak_end, b"edts")
        elst = _mp4_child(moov, edts[0], edts[1], b"elst") if edts else None
        edits = _parse_mp4_edits(moov, elst)

        media_times = [
            _movie_position_to_media_time(position, movie_scale, track_scale, edits)
            for position in positions
        ]
        sample_indices = _presentation_samples_for_media_times(media_times, stts_entries, ctts_entries)

        samples = []
        for position, sample_index in zip(positions, sample_indices):
            description_index = _sample_description_for_sample(sample_index, stsc_entries, chunk_count)
            if description_index is None or description_index > len(descriptions):
                raise ValueError(f"Keine eindeutige STSD-Zuordnung bei {position:.3f}s")
            description = descriptions[description_index - 1]
            sar = description["sar"]
            width, height = description["width"], description["height"]
            if sar is None or width <= 0 or height <= 0:
                raise ValueError(
                    f"STSD {description_index} hat keine eindeutige H.264-SPS/VUI-SAR"
                )
            sar_num, sar_den = sar
            dar = Fraction(width * sar_num, height * sar_den)
            samples.append({
                "position": position,
                "width": width,
                "height": height,
                "sar": f"{sar_num}:{sar_den}",
                "dar": f"{dar.numerator}:{dar.denominator}",
                "stsd": description_index,
            })
        return Mp4AspectMap(
            is_mp4=True,
            stsd_count=len(descriptions),
            samples=tuple(samples),
        )
    except (IndexError, KeyError, TypeError, ValueError, struct.error, ZeroDivisionError) as exc:
        stsd_count = len(descriptions) if "descriptions" in locals() else 0
        return Mp4AspectMap(is_mp4=True, stsd_count=stsd_count, error=str(exc))


def probe_showinfo_sample(video, position, ffmpeg):
    position_text = format(position, ".3f")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-nostdin",
                "-loglevel", "info",
                "-ss", position_text,
                "-i", str(video),
                "-t", str(int(ASPECT_SAMPLE_SECONDS)),
                "-map", "0:v:0",
                "-an", "-sn", "-dn",
                "-vf", "showinfo=checksum=0",
                "-f", "null",
                "NUL" if os.name == "nt" else "/dev/null",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    observations = []
    for line in completed.stdout.splitlines():
        if "showinfo" not in line or " n:" not in line:
            continue
        sar = SHOWINFO_SAR_RE.search(line)
        size = SHOWINFO_SIZE_RE.search(line)
        if not sar or not size:
            continue
        sar_num, sar_den = int(sar.group(1)), int(sar.group(2))
        width, height = int(size.group(1)), int(size.group(2))
        if sar_den <= 0 or width <= 0 or height <= 0:
            continue
        normalized = Fraction(sar_num, sar_den)
        observations.append((width, height, normalized.numerator, normalized.denominator))

    if not observations:
        return None

    width, height, sar_num, sar_den = Counter(observations).most_common(1)[0][0]
    dar = Fraction(width * sar_num, height * sar_den)
    return {
        "position": position,
        "width": width,
        "height": height,
        "sar": f"{sar_num}:{sar_den}",
        "dar": f"{dar.numerator}:{dar.denominator}",
    }


def decide_aspect_ratio(
    video,
    keeps,
    rate100,
    sample_probe=probe_showinfo_sample,
    mp4_probe=probe_mp4_active_sps_samples,
):
    ffprobe = find_media_executable("ffprobe.exe")
    if ffprobe is None:
        return AspectDecision(
            description="Videoauflösung und PAL-Ratio konnten nicht geprüft werden.",
            warning="ffprobe wurde nicht gefunden; Aspect Ratio wird nicht erzwungen.",
        )

    geometry = probe_video_geometry(video, ffprobe)
    if geometry is None:
        return AspectDecision(
            description="Videoauflösung und PAL-Ratio konnten nicht geprüft werden.",
            warning="Videoauflösung konnte nicht bestimmt werden; Aspect Ratio wird nicht erzwungen.",
        )

    width, height = geometry
    if width not in PAL_SD_WIDTHS or height != PAL_SD_HEIGHT:
        return AspectDecision(
            description=f"{width}x{height} ist kein PAL-SD-Risikofall; bisherige Containerkonfiguration bleibt aktiv."
        )

    positions = get_keep_sample_positions(keeps, rate100)
    samples = []
    multi_stsd = False
    mp4_map = Mp4AspectMap()
    if video.is_file() and video.suffix.lower() == ".mp4":
        mp4_map = mp4_probe(video, positions)
        if mp4_map.error and mp4_map.stsd_count != 1:
            return AspectDecision(
                description=f"PAL-SD {width}x{height}: MP4-STSD/SPS-Zuordnung nicht eindeutig.",
                warning=f"{mp4_map.error}; Aspect Ratio wird nicht erzwungen.",
            )
        multi_stsd = mp4_map.is_mp4 and mp4_map.stsd_count > 1

    if multi_stsd:
        samples = list(mp4_map.samples)
        if len(samples) != len(positions):
            return AspectDecision(
                description=f"PAL-SD {width}x{height}: Multi-STSD-Zuordnung unvollstaendig.",
                warning="Nicht jede Keep-Position konnte eindeutig einem STSD/SPS-Eintrag zugeordnet werden; "
                        "Aspect Ratio wird nicht erzwungen.",
            )
    else:
        ffmpeg = find_media_executable("ffmpeg.exe")
        if ffmpeg is None:
            return AspectDecision(
                description=f"PAL-SD {width}x{height}: keine automatische Ratio-Entscheidung.",
                warning="ffmpeg wurde nicht gefunden; Aspect Ratio wird nicht erzwungen.",
            )
        for position in positions:
            sample = sample_probe(video, position, ffmpeg)
            if sample is not None:
                samples.append(sample)

    sample_summary = tuple(
        (
            f"{sample['position']:.3f}s=STSD {sample['stsd']},"
            f"{sample['width']}x{sample['height']},SAR {sample['sar']},DAR {sample['dar']}"
            if "stsd" in sample else
            f"{sample['position']:.3f}s={sample['width']}x{sample['height']},"
            f"SAR {sample['sar']},DAR {sample['dar']}"
        )
        for sample in samples
    )
    required = max(MIN_VALID_ASPECT_SAMPLES, min(4, len(positions)))
    if len(samples) < required:
        return AspectDecision(
            description=f"PAL-SD {width}x{height}: Ratio nicht ausreichend messbar.",
            warning=(
                f"Nur {len(samples)} von mindestens {required} erforderlichen Keep-Stichproben waren verwertbar; "
                "Aspect Ratio wird nicht erzwungen."
            ),
            samples=sample_summary,
        )

    observed_sizes = {(sample["width"], sample["height"]) for sample in samples}
    observed_dars = {sample["dar"] for sample in samples}
    if observed_sizes != {(width, height)}:
        return AspectDecision(
            description=f"PAL-SD {width}x{height}: wechselnde Auflösung in den Keep-Segmenten.",
            warning="Die Keep-Stichproben melden unterschiedliche Auflösungen; Aspect Ratio wird nicht erzwungen.",
            samples=sample_summary,
        )

    target = None
    if observed_dars == {"16:9"}:
        target = Fraction(16, 9)
    elif observed_dars == {"4:3"}:
        target = Fraction(4, 3)

    if target is None:
        observed = ", ".join(sorted(observed_dars)) or "keine"
        return AspectDecision(
            description=f"PAL-SD {width}x{height}: Keep-DAR gemischt oder unbekannt ({observed}).",
            warning="Keine eindeutige PAL-Ratio; Aspect Ratio wird nicht automatisch erzwungen.",
            samples=sample_summary,
        )

    display_width_fraction = height * target
    if display_width_fraction.denominator != 1:
        return AspectDecision(
            description=f"PAL-SD {width}x{height}: Ziel-DAR {target.numerator}:{target.denominator} nicht darstellbar.",
            warning="Display-Breite ist nicht ganzzahlig; Aspect Ratio wird nicht erzwungen.",
            samples=sample_summary,
        )

    expected_dar = f"{target.numerator}:{target.denominator}"
    display_width = display_width_fraction.numerator
    return AspectDecision(
        force=True,
        aspect_ratio=4,
        display_width=display_width,
        expected_dar=expected_dar,
        description=(
            f"PAL-SD {width}x{height}: Keep-Material stabil {expected_dar}"
            f" ({'aktive STSD/SPS-Zuordnung' if multi_stsd else 'V6-showinfo'}); "
            f"Avidemux Custom-DAR mit Display-Breite {display_width}."
        ),
        samples=sample_summary,
    )


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
    last_phase_line = None
    phase_line_active = False
    stop_after_current = False
    aborted = False

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    label = display_video_name(video_name)
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
                    if line == last_phase_line:
                        continue
                    last_phase_line = line
                    phase_line_active = replace_status_line(line)
                    continue
                if line.upper().startswith(("WARNUNG", "FEHLER")):
                    clear_status_line(phase_line_active)
                    phase_line_active = False
                    last_phase_line = None
                    print(line)

            key = key_reader()
            if key == "b" and not stop_after_current:
                clear_status_line(phase_line_active)
                phase_line_active = False
                stop_after_current = True
                print("Batch-Stopp angefordert.")
                print("Aktueller Film wird noch fertig analysiert.")
                print("Danach Rückkehr ins Hauptmenü.")
            elif key == "x":
                clear_status_line(phase_line_active)
                phase_line_active = False
                aborted = True
                print("Sofortabbruch angefordert. Analyseprozessbaum wird beendet.")
                stop_process_tree(process)
                break
            time.sleep(0.05)

        returncode = process.wait()
        elapsed = format_elapsed(time.monotonic() - started)
        clear_status_line(phase_line_active)
        phase_line_active = False
        if aborted:
            print(colour(f"[{index}/{total}] ABBRUCH  {label} | {elapsed}", ANSI_RED))
        else:
            result_txt = Path(cwd) / Path(video_name).with_suffix(".txt").name
            successful = is_complete_comskip_txt(result_txt)
            status = (
                "OK"
                if successful
                else f"FEHLER {returncode}" if returncode not in (0, 1)
                else "FEHLER KEINE TXT"
            )
            ansi = ANSI_BLUE if successful else ANSI_RED
            print(colour(f"[{index}/{total}] ENDE   {label} | {elapsed} | {status}", ansi))
        return AnalysisProcessResult(returncode, stop_after_current, aborted)

    except KeyboardInterrupt:
        clear_status_line(phase_line_active)
        phase_line_active = False
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
        clear_status_line(phase_line_active)
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


def prepare_avidemux_project(video, txt):
    total_frames, rate100, ads = parse_comskip_txt(txt)
    frame_us = int(round(100_000_000 / rate100))

    keeps = build_keep_segments(total_frames, ads)
    if not keeps:
        raise ValueError("Kein Filmsegment übrig.")

    aspect = decide_aspect_ratio(video, keeps, rate100)

    vp = video.resolve().as_posix().replace('"', '\\"')
    out = [
        "#PY  <- Needed to identify #",
        "#--automatically built: Comskip -> Avidemux 2.8.1--",
        f"# ComskipExpectedDAR={aspect.expected_dar}",
        f"# ComskipAspectDecision={aspect.description}",
        *[f"# ComskipAspectSample={sample}" for sample in aspect.samples],
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
        (
            'adm.setContainer("MP4", "muxerType=0", "optimize=1", '
            f'"forceAspectRatio={aspect.force}", "aspectRatio={aspect.aspect_ratio}", '
            f'"displayWidth={aspect.display_width}", "rotation=0", "clockfreq=0")'
        ),
    ]
    return "\n".join(out) + "\n", aspect


def avidemux_project_text(video, txt):
    project_text, _aspect = prepare_avidemux_project(video, txt)
    return project_text


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

    project_text, aspect = prepare_avidemux_project(video, txt)
    launcher_text = avidemux_start_bat(project)

    project.write_text(project_text, encoding="utf-8")
    launcher.write_text(launcher_text, encoding="utf-8-sig")

    remove_artifacts(
        video,
        (MANUAL_SUFFIX, MANUAL_START_SUFFIX, APPROVED_SUFFIX, START_SUFFIX),
    )

    print("Aspect Ratio:", aspect.description)
    if aspect.warning:
        print("WARNUNG:", aspect.warning)

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
        label = display_video_name(video.name)
        print(colour(f"[{idx}/{total}] VORHANDEN  {label}", ANSI_BLUE))
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
