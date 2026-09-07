# Diagnose für Barbarian Queen und London Town

1. `_Workflow/WeDo Rueckfall-Diagnose Start.bat` öffnen.
2. Den Ordner mit den beiden Original-MP4s eingeben oder ins Fenster ziehen und Enter drücken.
3. Beide Diagnosen laufen automatisch. Am Ende liegt im gewählten Filmordner
   `WeDo-Rueckfall-Diagnose-<Zeitstempel>.zip`. Dieses ZIP zur Auswertung zurückgeben.

Es werden ausschließlich diese Dateinamen verwendet:

- `2026-09-04_04-35_Barbarian-Queen_wedo-movies_hd.mp4`
- `2026-09-07_11-11_London-Town_wedo-movies_hd.mp4`

Die Erkennungsregeln entsprechen dem v3-Test. Der Starter untersucht den Lernweg
und die grobe Suche bis zur Rückfallentscheidung. Er meldet ausdrücklich, ob
keine Suchfenster entstehen, die Abdeckung mehr als 60 Prozent beträgt oder
der neue Weg akzeptiert würde. Auch Lern-/Lesefehler werden getrennt erfasst.
Ein zusätzlicher Scan des roten Layouts über die Aufnahme zeigt, ob die
Suchfenster die bestätigten roten Blöcke abdecken.

Enthalten sind Einstellungen, Prüfsummen der verwendeten Werkzeuge, bestehende
Ergebnisdateien als Kopie, Lernprotokolle und Masken, die tatsächliche
Logo-Bildreferenz, alle Stichprobenwerte, Vorschaubilder mit Logo-Ausschnitten,
Suchfenster samt auslösenden Zeitpunkten sowie der Rotlayout-Kontrollscan.
Das ZIP enthält keine MP4s. Temporäre Lernclips werden entfernt.

Die vollständige alte Analyse und die native Werbeendprüfung werden nicht gestartet.
Originalvideos und vorhandene Schnittdateien bleiben unverändert. Wegen der
zusätzlichen Diagnoseausgaben sind diese Laufzeiten kein Geschwindigkeitsvergleich.

Der Starter benötigt die neue `comskip-wedo-diagnose.exe` im übergeordneten
ComSkip-Ordner neben den bestehenden `comskip.exe`, `ffmpeg.exe`, `ffprobe.exe`
und `comskip.ini`. Python muss beim Nutzer nicht installiert werden.
Der normale v3-Teststarter und die Originalversion behalten ihre bestehenden EXEs.

Build im Testbranch: `tools/build_wedo_diagnostic.ps1 -Python <python.exe>`.
