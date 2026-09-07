# Separater WeDo-Testbuild

Branch: `feature/wedo-sparse-local`, Ausgangsstand: `3ac73d7` auf `custom`.

Die `comskip-final.exe` behält den bisherigen Erkennungsweg. Beide EXEs enthalten
seit `video-end-fix-1` die Begrenzung von Lesezugriffen auf vorhandene Videoframes.
Der normale Starter bleibt unverändert.
Der Testbuild heißt `comskip-wedo-test.exe`. Zum Testen den separaten Starter
`_Workflow/Werbung entfernen WeDo-Test Start.bat` öffnen. Dieser verwendet die
Test-EXE ausschließlich für Dateinamen mit `wedo-movies`; alle anderen Sender
laufen mit der bisherigen EXE. Für bereits analysierte Filme im Menü `R`
wählen: Die bestehende Workflow-Sicherung der bisherigen Ergebnisse bleibt aktiv.

Der neue Weg lernt das normale Senderlogo in fünf Ausschnitten. Danach sucht
er alle 20 Sekunden nach Logo-Ausfällen und dem roten Werbelayout. Auch ein
einzelner Ausfall öffnet ein Suchfenster. Nur diese Fenster werden mit einem
Bild pro Sekunde auf das bisherige 90–135-Sekunden-Layout geprüft. Die
Logo-Rückkehr wird anschließend lokal untersucht; nur die Rückkehrkante und
der bisherige WeDo-Bumper-Rückblick benötigen einzelne Frames.

Die roten Layoutregeln und die Bumper-Erkennung werden unverändert verwendet.
Die neue Logo-Bewertung verwendet eine Bildreferenz im von Comskip gelernten
Logo-Rechteck. Die äußeren Dateiränder sind grobe Logo-Marker und müssen bei
der Sichtprüfung kontrolliert werden.

Bei fehlendem zuverlässigem Logo, unvollständigen Messungen, fehlender
Bestätigung, fehlender Logo-Rückkehr oder mehr als 60 Prozent lokaler
Suchabdeckung läuft automatisch der bisherige WeDo-Weg. Der Grund steht im
normalen Log und in der Diagnose-JSON (`wedo_sparse_fallback`). Erfolgreiche
Testläufe haben `processing_mode: wedo-sparse-local-v1`; ihre Diagnose enthält
Stichproben, Suchfenster, Treffer und Phasenlaufzeiten.

Direkter Vergleich mit demselben Testprogramm:

```powershell
.\comskip-wedo-test.exe "Film_wedo-movies_hd.mp4"
.\comskip-wedo-test.exe --wedo-scan legacy "Film_wedo-movies_hd.mp4"
```

Direkte EXE-Aufrufe schreiben die Analyseausgaben neben den Film; für die
automatische Sicherung vorheriger Ergebnisse den Workflow mit `R` verwenden.
`--wedo-movies-mode off` und `shadow` behalten ihren bisherigen Ablauf.

Die Trefferqualität und die tatsächliche Zeitersparnis sind noch mit echten
Aufnahmen zu vergleichen. Es wurden keine produktiven Filme automatisch getestet.

Die acht Rückfälle aus dem ersten Vergleichslauf wurden durch eine Stichprobe
am exklusiven Videoende ausgelöst: Die Containerdauer war wenige Millisekunden
länger als die Videospur. Das globale Raster und die lokale Logo-Endprüfung
verwenden jetzt höchstens `(Frameanzahl - 1) / fps` als Lesezeitpunkt. Gemeinsame
Einzelbildabfragen und die Bumper-Prüfung sind ebenfalls begrenzt. Die ersten
und letzten sechs Minuten bleiben vom Logo-Lernen ausgeschlossen. Echte
Lesefehler innerhalb des Videos lösen weiterhin den bisherigen Rückfall aus.

Reproduzierbarer separater Build aus dem Repository (Python mit den Paketen
aus `requirements-build.txt`): `tools/build_wedo_test.ps1 -Python <python.exe>`.
Der Build führt die gezielten Tests aus und schreibt nur `comskip-wedo-test.exe`.
