# ComSkip V4.3 MULTI-STSD – 02.10.2026

Diese Version baut auf dem akzeptierten V4.1-WeDo-v3-Teststand auf. Die
Werbeerkennung und `comskip-final.exe` bleiben unverändert. Neu ist die
korrekte PAL-SD-Aspect-Ratio-Behandlung im Avidemux-Workflow.

## Start

`_Workflow/Werbung entfernen Start.bat` öffnen. Menü und Bedienung bleiben gleich:
analysieren, offene Filme prüfen oder eine Aufnahme mit `R` erneut analysieren.
Anfang und Ende der Aufnahmen werden bei Bedarf manuell beschnitten.
Die bestehenden Programme zum finalen Schneiden und ihre Handbücher liegen
ebenfalls unter `_Workflow`.

## Erkennung

- WeDo: bisheriges Logo-Lernen, grobe Suche im 20-Sekunden-Raster, lokale
  Bestätigung des roten Layouts und native v1-Prüfung der Werbeenden.
- Die Grenze für die lokale Suchabdeckung bleibt **60 %**. Bei Bedarf erfolgt
  automatisch die vollständige bisherige Analyse.
- Die native Endprüfung behält ihre bisherigen Fenster: 30 Sekunden Vorlauf,
  bis zu 180 Sekunden Suche und 30 Sekunden Nachlauf.
- Andere Sender behalten ihre bisherigen Erkennungsprofile.
- Die Begrenzung der Einzelbildabfragen auf vorhandene Videobilder bleibt aktiv.

Es wurden keine weiteren Geschwindigkeitsoptimierungen übernommen: weder eine
70-%-Grenze noch kürzere Endprüfungen oder ein anderes Logo-Lernen.
Der diagnostische Verfahrensname `wedo-sparse-local-native-tail-v2` bleibt zur
Vergleichbarkeit der Ergebnisdateien erhalten; der Erkennungskern entspricht V4.1 FINAL.

## Aspect Ratio beim finalen Schnitt

Bei PAL-SD-Aufnahmen mit 720×576 oder 704×576 untersucht der Generator mehrere
dekodierte Stichproben ausschließlich innerhalb der tatsächlich behaltenen
Filmsegmente. Die bewährte FFmpeg-`showinfo`-Auswertung unterscheidet stabiles
16:9 von stabilem 4:3, auch wenn Vorlauf oder Werbung ein anderes Format haben.

Enthält eine MP4 mehrere `stsd`-Videobeschreibungen, wird `showinfo` nicht als
alleinige Quelle verwendet. Der Generator ordnet jede Keep-Position über die
MP4-Zeit- und Sampletabellen einschließlich `elst` und `ctts` dem korrekten
Präsentations-Sample, Chunk und aktiven `sample_description_index` zu und liest
die SAR aus der H.264-SPS/VUI des dazugehörigen `avcC`-Eintrags. Unterschiedliche aktive
Ratios oder eine nicht eindeutige Zuordnung führen zu einer sichtbaren Warnung
und niemals zu einer stillen automatischen Festlegung.

- stabiles 16:9: Avidemux Custom-DAR mit Display-Breite 1024
- stabiles 4:3: Avidemux Custom-DAR mit Display-Breite 768
- gemischt oder unklar: keine stille Ratio-Erzwingung, sichtbare Warnung
- HD und andere Auflösungen: bisherige Behandlung unverändert

Das Avidemux-Projekt enthält zusätzlich das erwartete DAR. Der finale
Schneide-Batch prüft neue und bereits vorhandene Finaldateien dagegen. Ein
720×576-Ergebnis mit SAR 1:1 / DAR 5:4 wird bei erwartetem 16:9 deshalb nicht
mehr als erfolgreich oder „bereits fertig“ akzeptiert. Video und Audio bleiben
weiterhin im Copy-Modus; der MKV-Fallback übernimmt dieselbe Ratio-Entscheidung.

## Akzeptierter Vergleich

Zwölf WeDo-Aufnahmen: zehn lokale Läufe und zwei vollständige Rückfälle.
Gesamtlaufzeit 41:19 statt 72:51 Minuten (43 % weniger). Die 86 bestätigten
Werbeblöcke der zehn lokalen Läufe stimmen an beiden Grenzen exakt mit v1
überein. Die Zeiten gelten für diesen Vergleich und sind keine feste Zusage
für weitere Aufnahmen. Bewertet wurden die Werbeblöcke; die Aufnahmeränder
beschneidet der Nutzer selbst.

## Sichern und wiederherstellen

Den **gesamten Ordner ComSkip** sichern. EXEs, DLLs, Senderlisten, INI und
`_Workflow` gehören zusammen. Zum Wiederherstellen den Ordner vollständig
zurückkopieren. Der normale Workflow benötigt weiterhin Python 3 sowie die
bisherige Umgebung für die abschließende Videobearbeitung.

`VERSION.txt` bezeichnet den Stand. `SHA256SUMS.txt` enthält die Prüfsummen
der mitgelieferten Dateien; eigene spätere Änderungen an Konfigurationen oder
Senderlisten ändern entsprechend deren Prüfsummen.

Die früheren Test-/Diagnoseprogramme und Entwicklungsübergaben sind nicht Teil
dieses finalen Auslieferungsordners. Der vorherige Ordner wurde separat im
Projektarchiv gesichert.
