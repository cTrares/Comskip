# ComSkip V4.1 FINAL – 07.09.2026

Diese Version übernimmt den akzeptierten WeDo-v3-Teststand in die normale
`comskip-final.exe`. Der separate WeDo-Teststarter wird nicht mehr benötigt.

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
Vergleichbarkeit der Ergebnisdateien erhalten; die Programmversion lautet V4.1 FINAL.

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
