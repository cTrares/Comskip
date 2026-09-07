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
Logo-Rückkehr wird seit `native-tail-2` mit dem nativen v1-Messweg untersucht.
Pro bestätigtem Werbeende wird ein verlustfreier Ausschnitt in Originalauflösung
erstellt: 30 Sekunden Vorlauf, bis zu 180 Sekunden Suche nach der Logo-Rückkehr
und 30 Sekunden Nachlauf für die zeitliche Bestätigung. Die Ausschnitte bleiben
innerhalb der Videospur und werden nach der Messung wieder entfernt.

Die roten Layoutregeln und die Bumper-Erkennung werden unverändert verwendet.
Die schnelle Vorauswahl verwendet weiterhin eine Bildreferenz im von Comskip
gelernten Logo-Rechteck. An den Werbeenden werden ausschließlich die nativen
`comskip_present`-Zustände mit derselben Maske und INI wie bei v1 ausgewertet.
Die bestehende v1-Schnittauswahl einschließlich Bumper-Rückblick wird direkt
wiederverwendet. So entscheidet ein einzelnes ähnliches Vorschaubild nicht mehr
über das Werbeende. Native Messdaten und Fenstergrenzen bleiben in der Diagnose
erhalten. Die äußeren Dateiränder sind weiterhin grobe Logo-Marker und müssen
bei der Sichtprüfung kontrolliert werden.

Bei fehlendem zuverlässigem Logo, unvollständigen Messungen, fehlender
Bestätigung, fehlender Logo-Rückkehr oder mehr als 60 Prozent lokaler
Suchabdeckung läuft automatisch der bisherige WeDo-Weg. Der Grund steht im
normalen Log und in der Diagnose-JSON (`wedo_sparse_fallback`).
Bei nicht ganzzahliger Bildrate wird ebenfalls der bisherige Weg verwendet,
damit sich das native Messraster durch den Ausschnitt nicht verschiebt.
Erfolgreiche Testläufe haben `processing_mode: wedo-sparse-local-native-tail-v2`; ihre Diagnose enthält
Stichproben, Suchfenster, Treffer und Phasenlaufzeiten.

Direkter Vergleich mit demselben Testprogramm:

```powershell
.\comskip-wedo-test.exe "Film_wedo-movies_hd.mp4"
.\comskip-wedo-test.exe --wedo-scan legacy "Film_wedo-movies_hd.mp4"
```

Direkte EXE-Aufrufe schreiben die Analyseausgaben neben den Film; für die
automatische Sicherung vorheriger Ergebnisse den Workflow mit `R` verwenden.
`--wedo-movies-mode off` und `shadow` behalten ihren bisherigen Ablauf.

Ein synthetischer Vergleich mit echtem FFmpeg und Comskip prüft identische
Werbeenden zwischen vollständigem v1-Messlauf und lokalem Messlauf. Ein kurz
eingeblendetes Logo während einer Vorschau wird dabei verworfen. Die Trefferqualität
und die Laufzeit sind erneut mit echten Aufnahmen zu vergleichen, insbesondere
mit den vier im ersten Testlauf falsch geschnittenen Filmen.

Die acht Rückfälle aus dem ersten Vergleichslauf wurden durch eine Stichprobe
am exklusiven Videoende ausgelöst: Die Containerdauer war wenige Millisekunden
länger als die Videospur. Das globale Raster verwendet jetzt höchstens
`(Frameanzahl - 1) / fps` als Lesezeitpunkt; lokale Clips enden mit der Videospur. Gemeinsame
Einzelbildabfragen und die Bumper-Prüfung sind ebenfalls begrenzt. Die ersten
und letzten sechs Minuten bleiben vom Logo-Lernen ausgeschlossen. Echte
Lesefehler innerhalb des Videos lösen weiterhin den bisherigen Rückfall aus.

Reproduzierbarer separater Build aus dem Repository (Python mit den Paketen
aus `requirements-build.txt`): `tools/build_wedo_test.ps1 -Python <python.exe>`.
Der Build führt die gezielten Tests aus und schreibt nur `comskip-wedo-test.exe`.
