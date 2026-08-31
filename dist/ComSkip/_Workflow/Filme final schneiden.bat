@echo off
setlocal DisableDelayedExpansion

set "DOWNLOADS=%FILME_FINAL_DOWNLOADS%"
if not defined DOWNLOADS for /f "usebackq delims=" %%I in (`powershell.exe -NoProfile -NonInteractive -Command "$k=Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders' -ErrorAction SilentlyContinue; $p=$k.'{374DE290-123F-4565-9164-39C4925E467B}'; if($p){[Environment]::ExpandEnvironmentVariables($p)}" 2^>nul`) do if not defined DOWNLOADS set "DOWNLOADS=%%I"
if not defined DOWNLOADS set "DOWNLOADS=%USERPROFILE%\Downloads"

set "FINAL_DIR=%DOWNLOADS%\Final"
set "LOG_DIR=%FINAL_DIR%\_logs"
set "WORK_DIR=%FINAL_DIR%\_work"
set "AVIDEMUX="
set "FFPROBE="
set "FFMPEG="
set "COMSKIP_DIR="
set "FOUND=0"
set "INDEX=0"
set "CREATED=0"
set "ALREADY_DONE=0"
set "FALLBACK_SUCCESS=0"
set "ERRORS=0"
set "ERROR_LIST_FILE="

echo Filme final schneiden
echo.

if not exist "%DOWNLOADS%" (
    echo FEHLER: Downloads-Ordner nicht gefunden: "%DOWNLOADS%"
    exit /b 1
)

for %%P in ("%DOWNLOADS%\*_Avidemux_CROP.py") do if exist "%%~fP" call :CountProject "%%~fP"

if "%FOUND%"=="0" goto Summary

call :FindAvidemux
if not defined AVIDEMUX (
    echo FEHLER: avidemux_cli.exe wurde nicht gefunden. Es wird nichts geschnitten.
    set "ERRORS=%FOUND%"
    goto FatalToolError
)

call :FindFfprobe
if not defined FFPROBE (
    echo FEHLER: ffprobe.exe wurde nicht gefunden. Es wird nichts geschnitten.
    set "ERRORS=%FOUND%"
    goto FatalToolError
)
call :FindFfmpeg

if not exist "%FINAL_DIR%" mkdir "%FINAL_DIR%" >nul 2>&1
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%" >nul 2>&1

if not exist "%LOG_DIR%" (
    echo FEHLER: Log-Ordner konnte nicht angelegt werden: "%LOG_DIR%"
    set "ERRORS=%FOUND%"
    goto FatalToolError
)
if not exist "%WORK_DIR%" (
    echo FEHLER: Arbeitsordner konnte nicht angelegt werden: "%WORK_DIR%"
    set "ERRORS=%FOUND%"
    goto FatalToolError
)

for /f "delims=" %%I in ('powershell.exe -NoProfile -NonInteractive -Command "[guid]::NewGuid().ToString('N')" 2^>nul') do if not defined RUN_ID set "RUN_ID=%%I"
if not defined RUN_ID set "RUN_ID=%RANDOM%%RANDOM%%RANDOM%"
set "ERROR_LIST_FILE=%WORK_DIR%\errors-%RUN_ID%.txt"
if exist "%ERROR_LIST_FILE%" del /q "%ERROR_LIST_FILE%" >nul 2>&1

for %%P in ("%DOWNLOADS%\*_Avidemux_CROP.py") do if exist "%%~fP" call :ProcessProject "%%~fP"
goto Summary

:CountProject
set "COUNT_NAME=%~n1"
if /i not "%COUNT_NAME:MANUELL=%"=="%COUNT_NAME%" exit /b 0
set /a FOUND+=1
exit /b 0

:FindAvidemux
for /f "delims=" %%I in ('where.exe avidemux_cli.exe 2^>nul') do if not defined AVIDEMUX set "AVIDEMUX=%%~fI"
if not defined AVIDEMUX if exist "C:\Program Files\Avidemux 2.8 VC++ 64bits\avidemux_cli.exe" set "AVIDEMUX=C:\Program Files\Avidemux 2.8 VC++ 64bits\avidemux_cli.exe"
if not defined AVIDEMUX if exist "%ProgramFiles%\Avidemux 2.8 VC++ 64bits\avidemux_cli.exe" set "AVIDEMUX=%ProgramFiles%\Avidemux 2.8 VC++ 64bits\avidemux_cli.exe"
if not defined AVIDEMUX if exist "%ProgramFiles%\Avidemux 2.8\avidemux_cli.exe" set "AVIDEMUX=%ProgramFiles%\Avidemux 2.8\avidemux_cli.exe"
if not defined AVIDEMUX if exist "%ProgramFiles%\Avidemux\avidemux_cli.exe" set "AVIDEMUX=%ProgramFiles%\Avidemux\avidemux_cli.exe"
if not defined AVIDEMUX if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Avidemux 2.8\avidemux_cli.exe" set "AVIDEMUX=%ProgramFiles(x86)%\Avidemux 2.8\avidemux_cli.exe"
exit /b 0

:FindFfprobe
for %%I in ("%~dp0..") do set "COMSKIP_DIR=%%~fI"
if exist "%COMSKIP_DIR%\ffprobe.exe" set "FFPROBE=%COMSKIP_DIR%\ffprobe.exe"
if not defined FFPROBE for /f "delims=" %%I in ('where.exe ffprobe.exe 2^>nul') do if not defined FFPROBE set "FFPROBE=%%~fI"
exit /b 0

:FindFfmpeg
if exist "%COMSKIP_DIR%\ffmpeg.exe" set "FFMPEG=%COMSKIP_DIR%\ffmpeg.exe"
if not defined FFMPEG for /f "delims=" %%I in ('where.exe ffmpeg.exe 2^>nul') do if not defined FFMPEG set "FFMPEG=%%~fI"
exit /b 0

:ProcessProject
set "PROJECT_NAME=%~n1"
if /i not "%PROJECT_NAME:MANUELL=%"=="%PROJECT_NAME%" exit /b 0

set /a INDEX+=1
set "PROJECT=%~f1"
set "BASE=%PROJECT_NAME:~0,-14%"
set "ORIGINAL=%DOWNLOADS%\%BASE%.mp4"
set "FINAL_FILE=%FINAL_DIR%\%BASE%.mp4"
set "LOG=%LOG_DIR%\%BASE%.avidemux.log"
set "TEMP_FILE=%WORK_DIR%\%BASE%.avidemux-work-%RUN_ID%.mp4"
set "PROBE_DATA=%WORK_DIR%\%BASE%.ffprobe-%RUN_ID%.txt"
set "BACKUP_FILE=%WORK_DIR%\%BASE%.previous-%RUN_ID%.mp4"
set "FALLBACK_SOURCE=%WORK_DIR%\%BASE%.avidemux-fallback-source.%RUN_ID%.mkv"
set "FALLBACK_PROJECT=%WORK_DIR%\%BASE%.avidemux-fallback-project.%RUN_ID%.py"
set "FALLBACK_FINAL=%WORK_DIR%\%BASE%.avidemux-fallback-final.%RUN_ID%.mp4"
set "REMUX_LOG=%LOG_DIR%\%BASE%.remux-fallback.log"
set "FALLBACK_AVID_LOG=%LOG_DIR%\%BASE%.avidemux-fallback.log"
set "FINAL_WAS_INVALID=0"

>"%LOG%" echo Filme final schneiden
>>"%LOG%" echo Projekt: "%PROJECT%"
>>"%LOG%" echo Original: "%ORIGINAL%"
>>"%LOG%" echo Ziel: "%FINAL_FILE%"
>>"%LOG%" echo Avidemux: "%AVIDEMUX%"
>>"%LOG%" echo ffprobe: "%FFPROBE%"
if defined FFMPEG >>"%LOG%" echo ffmpeg: "%FFMPEG%"
if not defined FFMPEG >>"%LOG%" echo ffmpeg: NICHT GEFUNDEN - normaler Ablauf bleibt verfuegbar.

if not exist "%ORIGINAL%" (
    >>"%LOG%" echo FEHLER: Originaldatei fehlt.
    echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... FEHLER
    call :MarkError
    exit /b 0
)

if exist "%FINAL_FILE%" (
    >>"%LOG%" echo Vorhandene Finaldatei wird validiert.
    call :ValidateVideo "%FINAL_FILE%" "%LOG%"
    if not errorlevel 1 (
        >>"%LOG%" echo BEREITS FERTIG: Vorhandene Finaldatei ist gueltig.
        echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... BEREITS FERTIG
        set /a ALREADY_DONE+=1
        exit /b 0
    )
    set "FINAL_WAS_INVALID=1"
    >>"%LOG%" echo Vorhandene Finaldatei ist ungueltig und bleibt bis zur erfolgreichen Neuerzeugung erhalten.
)

if exist "%TEMP_FILE%" del /q "%TEMP_FILE%" >>"%LOG%" 2>&1
if exist "%PROBE_DATA%" del /q "%PROBE_DATA%" >>"%LOG%" 2>&1
if exist "%BACKUP_FILE%" del /q "%BACKUP_FILE%" >>"%LOG%" 2>&1

>>"%LOG%" echo Avidemux wird gestartet.
"%AVIDEMUX%" --run "%PROJECT%" --save "%TEMP_FILE%" --quit >>"%LOG%" 2>&1
set "AVIDEMUX_EXIT=%ERRORLEVEL%"
>>"%LOG%" echo Avidemux Exit-Code: %AVIDEMUX_EXIT%

if not "%AVIDEMUX_EXIT%"=="0" (
    call :HandleNormalAvidemuxFailure
    exit /b 0
)

if not exist "%TEMP_FILE%" (
    >>"%LOG%" echo FEHLER: Avidemux hat keine temporaere Datei erzeugt.
    echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... FEHLER
    call :MarkError
    exit /b 0
)

set "TEMP_SIZE=0"
for %%S in ("%TEMP_FILE%") do set "TEMP_SIZE=%%~zS"
if "%TEMP_SIZE%"=="0" (
    >>"%LOG%" echo FEHLER: Die temporaere Datei ist leer.
    del /q "%TEMP_FILE%" >>"%LOG%" 2>&1
    echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... FEHLER
    call :MarkError
    exit /b 0
)

>>"%LOG%" echo Temporaere Datei wird mit ffprobe validiert.
call :ValidateVideo "%TEMP_FILE%" "%LOG%"
if errorlevel 1 (
    >>"%LOG%" echo FEHLER: Die temporaere Datei ist kein brauchbares Video.
    del /q "%TEMP_FILE%" >>"%LOG%" 2>&1
    echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... FEHLER
    call :MarkError
    exit /b 0
)

call :PromoteTemp
if errorlevel 1 (
    >>"%LOG%" echo FEHLER: Die validierte temporaere Datei konnte nicht zur Finaldatei werden.
    >>"%LOG%" echo Die temporaere Datei bleibt zur Diagnose erhalten: "%TEMP_FILE%"
    echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... FEHLER
    call :MarkError
    exit /b 0
)

>>"%LOG%" echo OK: Finaldatei wurde erfolgreich erstellt.
echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... OK
set /a CREATED+=1
exit /b 0

:HandleNormalAvidemuxFailure
>>"%LOG%" echo Normaler Avidemux-Versuch fehlgeschlagen.
set "SAVE_STARTED=0"
set "NORMAL_TEMP_VALID=0"
findstr.exe /i /c:"save-->" "%LOG%" >nul 2>&1
if not errorlevel 1 set "SAVE_STARTED=1"
if "%SAVE_STARTED%"=="1" >>"%LOG%" echo save--^> erkannt: JA
if "%SAVE_STARTED%"=="0" >>"%LOG%" echo save--^> erkannt: NEIN

if exist "%TEMP_FILE%" (
    >>"%LOG%" echo Trotz Fehler vorhandene temporaere Ausgabe wird geprueft.
    call :ValidateVideo "%TEMP_FILE%" "%LOG%"
    if not errorlevel 1 set "NORMAL_TEMP_VALID=1"
)

if "%SAVE_STARTED%"=="1" (
    >>"%LOG%" echo Fallback-Entscheidung: NEIN
    >>"%LOG%" echo Kein MKV-Fallback: Der Speichervorgang save--^> hatte bereits begonnen.
    goto NormalAvidemuxFinalError
)
if "%NORMAL_TEMP_VALID%"=="1" (
    >>"%LOG%" echo Fallback-Entscheidung: NEIN
    >>"%LOG%" echo Kein MKV-Fallback: Die temporaere Ausgabe ist bereits erfolgreich validierbar.
    goto NormalAvidemuxFinalError
)

>>"%LOG%" echo Fallback-Entscheidung: JA
>>"%LOG%" echo MKV-Fallback-Kriterium erfuellt: Exit-Code ungleich 0, save--^> fehlt und keine valide temporaere Ausgabe vorhanden.
echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... MP4-LADEFEHLER
call :TryMkvFallback
if not errorlevel 1 (
    echo        FALLBACK ERFOLGREICH
    set /a CREATED+=1
    set /a FALLBACK_SUCCESS+=1
    exit /b 0
)
if exist "%TEMP_FILE%" del /q "%TEMP_FILE%" >>"%LOG%" 2>&1
echo        FALLBACK FEHLGESCHLAGEN
call :MarkError
exit /b 0

:NormalAvidemuxFinalError
if exist "%TEMP_FILE%" del /q "%TEMP_FILE%" >>"%LOG%" 2>&1
echo [%INDEX%/%FOUND%] "%BASE%.mp4" ... FEHLER
call :MarkError
exit /b 0

:TryMkvFallback
set "NORMAL_TEMP_FILE=%TEMP_FILE%"
>"%REMUX_LOG%" echo MKV-Remux-Fallback fuer "%BASE%.mp4"
>>"%REMUX_LOG%" echo Original: "%ORIGINAL%"
>>"%REMUX_LOG%" echo MKV-Zwischenquelle: "%FALLBACK_SOURCE%"
>"%FALLBACK_AVID_LOG%" echo Avidemux-MKV-Fallback fuer "%BASE%.mp4"
>>"%FALLBACK_AVID_LOG%" echo Originalprojekt: "%PROJECT%"
>>"%FALLBACK_AVID_LOG%" echo Temporaeres Projekt: "%FALLBACK_PROJECT%"
>>"%LOG%" echo MKV-Fallback wird einmalig gestartet.

if exist "%FALLBACK_SOURCE%" del /q "%FALLBACK_SOURCE%" >>"%REMUX_LOG%" 2>&1
if exist "%FALLBACK_PROJECT%" del /q "%FALLBACK_PROJECT%" >>"%FALLBACK_AVID_LOG%" 2>&1
if exist "%FALLBACK_FINAL%" del /q "%FALLBACK_FINAL%" >>"%FALLBACK_AVID_LOG%" 2>&1

echo        Fallback: Original mit ffprobe pruefen ...
>>"%REMUX_LOG%" echo Original wird vor dem Fallback mit ffprobe validiert.
call :ValidateVideo "%ORIGINAL%" "%REMUX_LOG%"
if errorlevel 1 (
    >>"%REMUX_LOG%" echo Original-ffprobe: FEHLER
    >>"%REMUX_LOG%" echo FEHLER: Original ist mit ffprobe nicht als brauchbares Video lesbar. Kein Remux.
    >>"%LOG%" echo MKV-Fallback abgebrochen: Original ist mit ffprobe ungueltig.
    exit /b 1
)
>>"%REMUX_LOG%" echo Original-ffprobe: OK
>>"%REMUX_LOG%" echo OK: Original ist mit ffprobe lesbar.

if not defined FFMPEG (
    >>"%REMUX_LOG%" echo FEHLER: ffmpeg.exe wurde nicht gefunden. Fallback nicht verfuegbar.
    >>"%LOG%" echo MKV-Fallback nicht verfuegbar: ffmpeg.exe wurde nicht gefunden.
    exit /b 1
)

>>"%REMUX_LOG%" echo ffmpeg: "%FFMPEG%"
>>"%REMUX_LOG%" echo Remux startet mit Video- und Audio-Stream-Copy.
echo        Fallback: verlustfreier Remux nach MKV ...
"%FFMPEG%" -hide_banner -nostdin -y -i "%ORIGINAL%" -map 0:v:0 -map 0:a:0? -c copy "%FALLBACK_SOURCE%" >>"%REMUX_LOG%" 2>&1
set "REMUX_EXIT=%ERRORLEVEL%"
>>"%REMUX_LOG%" echo ffmpeg Remux Exit-Code: %REMUX_EXIT%
if not "%REMUX_EXIT%"=="0" (
    >>"%REMUX_LOG%" echo FEHLER: MKV-Remux fehlgeschlagen.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: ffmpeg-Remux Exit-Code %REMUX_EXIT%.
    exit /b 1
)

>>"%REMUX_LOG%" echo MKV-Zwischenquelle wird mit ffprobe validiert.
call :ValidateVideo "%FALLBACK_SOURCE%" "%REMUX_LOG%"
if errorlevel 1 (
    >>"%REMUX_LOG%" echo Fallback-MKV validiert: NEIN
    >>"%REMUX_LOG%" echo FEHLER: MKV-Zwischenquelle ist nicht valide. Avidemux-Fallback wird nicht gestartet.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: Remux-Datei ist ungueltig.
    exit /b 1
)
>>"%REMUX_LOG%" echo Fallback-MKV validiert: JA
>>"%REMUX_LOG%" echo OK: MKV-Zwischenquelle ist validiert.
echo        Fallback: MKV OK

set "CROP_PROJECT=%PROJECT%"
set "CROP_ORIGINAL=%ORIGINAL%"
set "CROP_FALLBACK_SOURCE=%FALLBACK_SOURCE%"
set "CROP_FALLBACK_PROJECT=%FALLBACK_PROJECT%"
powershell.exe -NoProfile -NonInteractive -Command "$text=[IO.File]::ReadAllText($env:CROP_PROJECT); $original=$env:CROP_ORIGINAL; $fallback=$env:CROP_FALLBACK_SOURCE; $paths=[Collections.Generic.List[string]]::new(); $paths.Add($original); $forward=$original.Replace('\','/'); if($forward -cne $original){$paths.Add($forward)}; $quotes=@([char]34,[char]39); $count=0; $hitToken=$null; $hitPath=$null; $hitAt=-1; foreach($path in $paths){foreach($quote in $quotes){$token='adm.loadVideo('+$quote+$path+$quote+')'; $from=0; while($from -le $text.Length){$at=$text.IndexOf($token,$from,[StringComparison]::OrdinalIgnoreCase); if($at -lt 0){break}; $count++; if($count -eq 1){$hitToken=$token; $hitPath=$path; $hitAt=$at}; $from=$at+$token.Length}}}; if($count -ne 1){Write-Error ('Exakter adm.loadVideo-Quellaufruf wurde nicht eindeutig gefunden. Treffer: '+$count); exit 2}; $replacementPath=$fallback; if($hitPath.Contains('/')){$replacementPath=$fallback.Replace('\','/')}; $replacementToken=$hitToken.Replace($hitPath,$replacementPath); $updated=$text.Substring(0,$hitAt)+$replacementToken+$text.Substring($hitAt+$hitToken.Length); [IO.File]::WriteAllText($env:CROP_FALLBACK_PROJECT,$updated,[Text.UTF8Encoding]::new($false)); exit 0" >>"%FALLBACK_AVID_LOG%" 2>&1
set "PROJECT_COPY_EXIT=%ERRORLEVEL%"
set "CROP_PROJECT="
set "CROP_ORIGINAL="
set "CROP_FALLBACK_SOURCE="
set "CROP_FALLBACK_PROJECT="
>>"%FALLBACK_AVID_LOG%" echo Fallback-Projekt Exit-Code: %PROJECT_COPY_EXIT%
if not "%PROJECT_COPY_EXIT%"=="0" (
    >>"%FALLBACK_AVID_LOG%" echo Temporaeres Projekt erzeugt: NEIN
    >>"%FALLBACK_AVID_LOG%" echo FEHLER: Exakter adm.loadVideo-Aufruf wurde im CROP-Projekt nicht eindeutig genau einmal gefunden. Keine heuristische Umschreibung.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: adm.loadVideo-Quellpfad im CROP-Projekt nicht eindeutig.
    exit /b 1
)
>>"%FALLBACK_AVID_LOG%" echo Temporaeres Projekt erzeugt: JA
>>"%FALLBACK_AVID_LOG%" echo OK: Temporaere Projektkopie mit MKV-Quellpfad wurde erzeugt.
echo        Fallback: CROP-Projekt vorbereitet

>>"%FALLBACK_AVID_LOG%" echo Avidemux-Fallback wird gestartet.
echo        Fallback: Avidemux ...
"%AVIDEMUX%" --run "%FALLBACK_PROJECT%" --save "%FALLBACK_FINAL%" --quit >>"%FALLBACK_AVID_LOG%" 2>&1
set "FALLBACK_AVID_EXIT=%ERRORLEVEL%"
>>"%FALLBACK_AVID_LOG%" echo Avidemux-Fallback Exit-Code: %FALLBACK_AVID_EXIT%
if not "%FALLBACK_AVID_EXIT%"=="0" (
    >>"%FALLBACK_AVID_LOG%" echo FEHLER: Avidemux-Fallback fehlgeschlagen. Es gibt keinen weiteren Versuch.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: Avidemux Exit-Code %FALLBACK_AVID_EXIT%.
    exit /b 1
)

if not exist "%FALLBACK_FINAL%" (
    >>"%FALLBACK_AVID_LOG%" echo FEHLER: Avidemux-Fallback hat keine temporaere Finaldatei erzeugt.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: Keine temporaere Finaldatei.
    exit /b 1
)
set "FALLBACK_FINAL_SIZE=0"
for %%S in ("%FALLBACK_FINAL%") do set "FALLBACK_FINAL_SIZE=%%~zS"
if "%FALLBACK_FINAL_SIZE%"=="0" (
    >>"%FALLBACK_AVID_LOG%" echo FEHLER: Temporaere Fallback-Finaldatei ist leer.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: Temporaere Finaldatei ist leer.
    exit /b 1
)

>>"%FALLBACK_AVID_LOG%" echo Temporaere Fallback-Finaldatei wird mit ffprobe validiert.
call :ValidateVideo "%FALLBACK_FINAL%" "%FALLBACK_AVID_LOG%"
if errorlevel 1 (
    >>"%FALLBACK_AVID_LOG%" echo Fallback-Finalvalidierung: FEHLER
    >>"%FALLBACK_AVID_LOG%" echo FEHLER: Temporaere Fallback-Finaldatei ist nicht valide.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: Finalvalidierung fehlgeschlagen.
    exit /b 1
)
>>"%FALLBACK_AVID_LOG%" echo Fallback-Finalvalidierung: OK
>>"%FALLBACK_AVID_LOG%" echo OK: Temporaere Fallback-Finaldatei ist validiert.

set "TEMP_FILE=%FALLBACK_FINAL%"
call :PromoteTemp
set "FALLBACK_PROMOTE_EXIT=%ERRORLEVEL%"
set "TEMP_FILE=%NORMAL_TEMP_FILE%"
if not "%FALLBACK_PROMOTE_EXIT%"=="0" (
    >>"%FALLBACK_AVID_LOG%" echo Promotion nach Final: FEHLER
    >>"%FALLBACK_AVID_LOG%" echo FEHLER: Validierte Fallback-Datei konnte nicht zur Finaldatei werden.
    >>"%LOG%" echo MKV-Fallback fehlgeschlagen: Promotion zur Finaldatei fehlgeschlagen.
    exit /b 1
)

>>"%FALLBACK_AVID_LOG%" echo Promotion nach Final: OK
>>"%FALLBACK_AVID_LOG%" echo OK: Fallback-Finaldatei wurde erfolgreich nach Final uebernommen.
>>"%LOG%" echo OK: Film wurde durch den einmaligen MKV-Fallback gerettet.
if exist "%NORMAL_TEMP_FILE%" del /q "%NORMAL_TEMP_FILE%" >>"%LOG%" 2>&1
if exist "%FALLBACK_SOURCE%" del /q "%FALLBACK_SOURCE%" >>"%REMUX_LOG%" 2>&1
if exist "%FALLBACK_PROJECT%" del /q "%FALLBACK_PROJECT%" >>"%FALLBACK_AVID_LOG%" 2>&1
exit /b 0

:ValidateVideo
if exist "%PROBE_DATA%" del /q "%PROBE_DATA%" >>"%~2" 2>&1
"%FFPROBE%" -v error -select_streams v:0 -show_entries stream=index -show_entries format=duration -of default=noprint_wrappers=1 "%~1" >"%PROBE_DATA%" 2>>"%~2"
set "PROBE_EXIT=%ERRORLEVEL%"
if exist "%PROBE_DATA%" type "%PROBE_DATA%" >>"%~2" 2>&1
if not "%PROBE_EXIT%"=="0" (
    if exist "%PROBE_DATA%" del /q "%PROBE_DATA%" >>"%~2" 2>&1
    exit /b 1
)
set "CROP_PROBE_DATA=%PROBE_DATA%"
powershell.exe -NoProfile -NonInteractive -Command "$hasVideo=$false; $duration=0.0; foreach($line in Get-Content -LiteralPath $env:CROP_PROBE_DATA){if($line -match '^index=\d+$'){$hasVideo=$true}; if($line -match '^duration=(.+)$'){$null=[double]::TryParse($Matches[1],[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$duration)}}; if($hasVideo -and $duration -gt 0){exit 0}; exit 1" >>"%~2" 2>&1
set "PROBE_VALID=%ERRORLEVEL%"
set "CROP_PROBE_DATA="
if exist "%PROBE_DATA%" del /q "%PROBE_DATA%" >>"%~2" 2>&1
if not "%PROBE_VALID%"=="0" exit /b 1
exit /b 0

:PromoteTemp
set "CROP_TEMP=%TEMP_FILE%"
set "CROP_FINAL=%FINAL_FILE%"
set "CROP_BACKUP=%BACKUP_FILE%"
if "%FINAL_WAS_INVALID%"=="1" (
    powershell.exe -NoProfile -NonInteractive -Command "try{[IO.File]::Replace($env:CROP_TEMP,$env:CROP_FINAL,$env:CROP_BACKUP,$true); exit 0}catch{Write-Error $_.Exception.Message; exit 1}" >>"%LOG%" 2>&1
) else (
    powershell.exe -NoProfile -NonInteractive -Command "try{[IO.File]::Move($env:CROP_TEMP,$env:CROP_FINAL); exit 0}catch{Write-Error $_.Exception.Message; exit 1}" >>"%LOG%" 2>&1
)
set "PROMOTE_EXIT=%ERRORLEVEL%"
set "CROP_TEMP="
set "CROP_FINAL="
set "CROP_BACKUP="
if not "%PROMOTE_EXIT%"=="0" exit /b 1
if exist "%BACKUP_FILE%" del /q "%BACKUP_FILE%" >>"%LOG%" 2>&1
exit /b 0

:MarkError
set /a ERRORS+=1
if defined ERROR_LIST_FILE >>"%ERROR_LIST_FILE%" echo "%BASE%.mp4"
exit /b 0

:FatalToolError
echo.
echo Betroffene Filme:
for %%P in ("%DOWNLOADS%\*_Avidemux_CROP.py") do if exist "%%~fP" call :ListProjectName "%%~fP"
goto Summary

:ListProjectName
set "LIST_NAME=%~n1"
if /i not "%LIST_NAME:MANUELL=%"=="%LIST_NAME%" exit /b 0
set "LIST_BASE=%LIST_NAME:~0,-14%"
echo   "%LIST_BASE%.mp4"
exit /b 0

:Summary
echo.
echo Filme final schneiden - abgeschlossen
echo.
echo Gefunden:                 %FOUND%
echo Neu erstellt:             %CREATED%
echo Bereits fertig:           %ALREADY_DONE%
echo Per Fallback gerettet:    %FALLBACK_SUCCESS%
echo Fehler:                   %ERRORS%
if not "%ERRORS%"=="0" if defined ERROR_LIST_FILE if exist "%ERROR_LIST_FILE%" (
    echo Fehlerhafte Filme:
    for /f "usebackq delims=" %%E in ("%ERROR_LIST_FILE%") do echo   %%E
)
if defined ERROR_LIST_FILE if exist "%ERROR_LIST_FILE%" del /q "%ERROR_LIST_FILE%" >nul 2>&1
echo.
pause
if not "%ERRORS%"=="0" exit /b 1
exit /b 0
