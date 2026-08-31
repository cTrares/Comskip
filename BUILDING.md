# Comskip V4 aus einem frischen Klon wiederherstellen

Dieses Repository enthält den selbst entwickelten Quellcode, Tests, die
Konfigurationen und die kleinen Workflow-Dateien. Fertige EXE- und DLL-Dateien
sind absichtlich nicht Teil der Git-Historie. Sie werden aus den dokumentierten
externen Abhängigkeiten neu erzeugt.

## Unterstützte Zielumgebung

Der produktive portable Build ist für Windows x64 vorgesehen. Der native
Comskip-Kern kann über die vorhandene GitHub-Actions-Matrix zusätzlich unter
Linux und macOS gebaut werden.

## Voraussetzungen unter Windows

1. Git for Windows.
2. Python 3.12 x64 einschließlich `venv` und `pip`.
3. MSYS2 x64, standardmäßig unter `C:\msys64`.
4. In einer MSYS2-MinGW64-Shell:

```bash
pacman -Syu
pacman -S --needed \
  mingw-w64-x86_64-gcc \
  mingw-w64-x86_64-make \
  mingw-w64-x86_64-autotools \
  mingw-w64-x86_64-libtool \
  mingw-w64-x86_64-pkg-config \
  mingw-w64-x86_64-yasm \
  mingw-w64-x86_64-argtable \
  mingw-w64-x86_64-ffmpeg \
  mingw-w64-x86_64-SDL2
```

Die Pakete stammen aus den offiziellen MSYS2-Repositories. Die Python-Pakete
und ihre geprüften Versionen stehen in `requirements-build.txt` und werden von
PyPI bezogen.

## Vollständiger Build

In einer normalen PowerShell im geklonten Repository:

```powershell
.\tools\build_windows.ps1
```

Das Skript:

1. erzeugt `comskip.exe` und `comskip-gui.exe` mit MSYS2,
2. legt eine isolierte Python-Umgebung unter `_temp` an,
3. installiert die festgelegten Python-Abhängigkeiten,
4. führt alle Python-Unittests aus,
5. baut `comskip-final.exe` mit PyInstaller,
6. sammelt FFmpeg und die transitiven MinGW-DLL-Abhängigkeiten und
7. stellt den portablen Ordner ausschließlich unter `dist\ComSkip` bereit.

Bei abweichenden Programmpfaden:

```powershell
.\tools\build_windows.ps1 -Python "C:\Pfad\python.exe" -Msys2Root "C:\msys64"
```

## Nur Tests und Python-Launcher

Wenn der native Teil bereits gebaut ist oder nur die Python-Seite geprüft
werden soll:

```powershell
.\tools\build_windows.ps1 -SkipNative
```

Der isolierte Python-Build liegt anschließend unter
`_temp\reproducible-build`. Dieser Ordner ist temporär und gehört nicht in Git.

## Portable Laufzeitdateien

Die kleinen, projektspezifischen Dateien unter `dist\ComSkip` sind bewusst in
Git enthalten. Dazu gehören die INI-/Dictionary-Dateien und der Workflow. Die
großen, wiederbeschaffbaren Programme und DLLs werden beim Build ergänzt.

Ein vollständiger portabler Ordner enthält mindestens:

- `comskip.exe`
- `ComskipGUI.exe`
- `comskip-final.exe`
- `ffmpeg.exe` und `ffprobe.exe`
- die von `package_windows_mingw.sh` ermittelten DLLs
- `comskip.ini` und `comskip.dictionary`
- `Makromodus-Sender.txt` und `Schnellmodus-Sender.txt`
- `_Workflow\Werbung entfernen.py` und die zugehörigen Start-/Schnittdateien

## Prüfung

Der lokale Build gilt als erfolgreich, wenn alle Unittests bestehen, die drei
Programme erzeugt wurden und der portable Smoke-Test ohne fehlende DLL startet.
GitHub Actions baut den nativen Code zusätzlich nach jedem Push und Pull
Request aus einem frischen Checkout.

Der Smoke-Test kann separat ausgeführt werden:

```powershell
.\tools\smoke_portable.ps1
```

Die erzeugten Binärdateien können separat als GitHub Release veröffentlicht
werden. Sie müssen nicht als normale Git-Dateien committed werden.
