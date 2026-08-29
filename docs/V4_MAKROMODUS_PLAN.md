# Comskip V4 – kommerzieller Logo-Makromodus

V4 zweigt ausschließlich vom gesicherten V3-Stand
`custom-2026-08-29-public-broadcaster-fast-mode` ab. V3 wird weder geändert
noch zusammengeführt.

## Ziel

Kommerzielle Aufnahmen sollen in höchstens ungefähr einer Minute grobe bis
lokal verfeinerte Werbeblöcke erhalten. Maßstab ist nicht die Anzahl
analysierter Frames, sondern vergleichbare Schnittqualität bei deutlich
geringerer Laufzeit.

## Getrennte Ausführungswege

1. Sender aus `Schnellmodus-Sender.txt`: unveränderter öffentlich-rechtlicher
   Schnellmodus aus V3.
2. `wedo-movies`: unveränderter eigener WeDo-Workflow.
3. Sender aus `Makromodus-Sender.txt`: neuer V4-Makromodus.
4. `--full-analysis`: unveränderter vollständiger V3/Comskip-Ablauf.

## Umsetzung in drei großen Messschritten

1. Dynamisches Logo je Aufnahme lernen und die gesamte Laufzeit zuerst in
   einem groben, progressiven Raster abdecken.
2. Lange stabile Filmblöcke bilden, kurze Logoaussetzer überbrücken und nur
   plausible lange Lücken als Werbung behandeln.
3. Nur die wenigen gefundenen Blockgrenzen lokal in einem Zwei-Sekunden-Raster
   nachprüfen. Schwarzbild-Snapping wird erst ergänzt, wenn der Vergleichslauf
   dafür einen messbaren Nutzen zeigt.

## Ein Vergleichslauf statt Testschleifen

Nach dem portablen Build wird der vorhandene kommerzielle Filmsatz einmal mit
V4 ausgeführt. Bewertet werden pro Film Laufzeit, Anzahl gefundener Blöcke,
Blocktreffer und Kantenabweichung gegenüber den gesicherten Schnittmarken.
Danach folgt genau eine gebündelte Korrekturrunde für die größten systematischen
Fehler. Die vollständige Analyse läuft nie automatisch als Zeitfalle an.
