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

1. Dynamisches Logo je Aufnahme aus über fast die gesamte Laufzeit verteilten
   Lernpunkten bestimmen und danach die gesamte Laufzeit zuerst in einem
   groben, progressiven Raster abdecken. Die Filmmitte ist kein Sonderanker.
   Falls der interne Heatmap-Lerner keinen Kandidaten findet, werden nur fünf
   kurze Fenster parallel mit Comskips bewährtem Logo-Lerner geprüft. Der
   vollständige Comskip-Sensordurchgang bleibt auch dann ausgeschaltet.
2. Zuerst kurze Logoaussetzer von höchstens 90 Sekunden an bereits stabile
   Filmzusammenhänge anbinden, erst danach die Mindestlänge von sieben Minuten
   auf Filmanker anwenden. Ein stabil positiver Abschnitt von mindestens 90
   Sekunden darf von einem Werbevorschlag nicht einfach überdeckt werden.
3. Nur die wenigen gefundenen Blockgrenzen lokal in einem Zwei-Sekunden-Raster
   nachprüfen. Fünf benachbarte Messungen werden dabei zeitlich per Median
   stabilisiert; ein einzelner dunkler oder texturierter Hintergrund darf ein
   sichtbares Logo nicht mehr bis zur nächsten zufällig hellen Szene verbergen.
   Bei einer mehrfach schwankenden Filmrückkehr wird die früheste Kante nur
   dann genommen, wenn danach mindestens 72 Prozent des restlichen lokalen
   Korridors logo-positiv bleiben. Ein einzelner Logo-Treffer innerhalb der
   Werbung kann die Kante deshalb nicht vorziehen.
   Weil echtes Senderlogo in Eigenwerbung semantisch nicht sicher
   von Film unterscheidbar ist, bekommt jede innere Logo-Rückkehr zusätzlich
   einen orangefarbenen Null-Längen-Prüfmarker 120 Sekunden hinter der
   automatischen Kante. `M`/`N` springt zu diesen Punkten; die EDL schneidet
   sie nicht. Damit bleibt ein Spezialfall begrenzt, statt minutenlanges
   manuelles Suchen zu erzwingen.

## Ein Vergleichslauf statt Testschleifen

Nach dem portablen Build wird der vorhandene kommerzielle Filmsatz einmal mit
V4 ausgeführt. Bewertet werden pro Film Laufzeit, Anzahl gefundener Blöcke,
Blocktreffer und Kantenabweichung gegenüber den gesicherten Schnittmarken.
Danach folgt genau eine gebündelte Korrekturrunde für die größten systematischen
Fehler. Die vollständige Analyse läuft nie automatisch als Zeitfalle an.

## Terminalausgabe

Jeder Analyseweg meldet seine aktuelle Phase und das aktive Modul. Während
einer laufenden Analyse wird nur ein gekürzter Filmtitel wiederholt; der lange
technische Dateiname bleibt den Auswahllisten und Diagnosedateien vorbehalten.
