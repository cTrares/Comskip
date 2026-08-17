# Phase 2C: Hybrid Logo Detection, True End-to-End Experiment

## Ergebnis in einem Satz

Der echte Hybridpfad behebt die bekannten Werbe-Fehlklassifikationen in
Freelance vollständig und erkennt 98,95 % der bekannten Werbung in American
Assassin, aber die vollständige Neutralisierung der Längenstrafe erzeugt
schwere Regressionen: In One Day as a Lion werden danach alle 29.259
bestätigten Showframes als Werbung klassifiziert, und beide guten Kontrollfilme
erhalten große neue Commercial-Endblöcke. Diese kombinierte Phase-2C-Variante
ist deshalb nicht produktionsreif.

## 1. Git-Zustand

- Repository: `D:\PythonProjekte\ComSkip Fork`
- Branch vor und nach dem Experiment: `feature/hybrid-logo-detection`
- HEAD vor und nach dem Experiment: `1d58e8f65cc4c821d7c546064377db6dd9e38761`
- Der Arbeitsbaum war und bleibt absichtlich unsauber. Vorhandene, uncommittete
  Phase-1/2A/2B-Arbeit wurde weder zurückgesetzt noch überschrieben.
- Endstatus im Comskip-Repository: `M comskip.c`, `?? tools/`.
- LogoFinder blieb unverändert. Sein Status ist weiterhin ausschließlich:
  `LogoFinder.db-shm`, `LogoFinder.db-wal`, `README.md` und
  `_cT Verbesserungen.txt` als untracked Dateien.
- Kein Commit, Push, Merge, Tag und keine Portable-Aktualisierung wurde
  ausgeführt.

## 2. Geänderte Dateien

- `comskip.c`: vorhandene Phase-1/2A/2B-Infrastruktur plus neuer, strikt
  opt-infähiger `--hybrid-logo-experimental`-Pfad, Erhalt der strukturellen
  LOGO-Verfügbarkeit, echte Fusionsnutzung, zwei gezielt deaktivierte
  excessive-length-Multiplikationen und Blockdiagnostik.
- `tools/hybrid_logo/hybrid_logo_analysis.py`: frameweise, sequenzielle
  LogoFinder-Auswertung nach einmaligem globalem Lernen.
- `tools/hybrid_logo/hybrid_logo_fusion.py`: dichte Frame-Timeline,
  zeitlich äquivalente Phase-2A-Stabilisierung und getrennte Sensorzustände.
- `tools/hybrid_logo/hybrid_logo_evaluate.py`: feste, inklusive
  Frame-Ground-Truth-Auswertung und Klassifikationsdifferenzen.
- `tools/hybrid_logo/test_hybrid_logo_fusion.py` und
  `tools/hybrid_logo/test_hybrid_logo_evaluate.py`: neue Regressionstests.
- Dieser Bericht.

LogoFinders Quellcode wurde nicht geändert. Comskips frühes Logo-Lernen,
Kantenmaske, `CheckStationLogoEdge`, Schwellen, Lernfenster und Sampleanzahl
wurden nicht geändert.

## 3. Genaue Hybrid-End-to-End-Architektur

Der Lauf bleibt zweistufig und bettet weder Python noch OpenCV in Comskip ein:

1. LogoFinder lernt einmal global Heatmap, Logo-Region und Medianreferenz.
2. Nur der gelernte kleine Crop wird sequenziell auf jeden dekodierbaren Frame
   angewandt. Es gibt dabei weder Decoder-Seeks noch neu berechnete Heatmaps.
3. Python schreibt eine versionierte, PTS-orientierte
   `hybrid-logo-v1`-Timeline. LogoFinder-Rohscore, stabilisierter Zustand,
   lokale Confidence und globale Reliability bleiben erhalten.
4. Comskips exportierte lokale Logo-Beobachtung bleibt ein separater Sensor:
   `currentGoodEdge`, lokaler Zustand/Confidence, globale `logoPercentage` und
   globale Reliability bleiben diagnostizierbar.
5. Die Fusion schreibt `PRESENT`, `ABSENT`, `CONFLICT` oder `UNKNOWN` pro
   Zeitpunkt. Ein belastbarer Sensor wird verwendet, wenn der andere unknown
   ist; Widerspruch bleibt ausdrücklich conflict.
6. Comskip validiert das Sidecar und aktiviert nur mit gültigem Sidecar plus
   `--hybrid-logo-experimental` den echten Pfad. PRESENT/ABSENT benutzen die
   vorhandenen Logo-Modifier; CONFLICT/UNKNOWN sind neutral.
7. Danach läuft die übrige normale Commercial Detection weiter. Es wurden
   keine künstlichen Fusions-Cutpoints hinzugefügt.

Ohne den Schalter bleibt das Programm im bisherigen Baselinepfad.

## 4. LogoFinder: frameweise Analyse

Alle angeforderten Frames wurden tatsächlich bewertet, insgesamt 1.064.750.
Die primäre Zeitachse ist `frame / container_fps`; alle fünf Dateien haben 25
fps. Der globale Lernschritt lief pro Film genau einmal.

| Film | geprüfte Frames | Crop | Heatmap-Confidence | rohe Schwellenwechsel |
| --- | ---: | --- | ---: | ---: |
| American Assassin | 214.750 | 634,72-667,117 | 0,3741 | 14.515 |
| Freelance | 214.750 | 634,76-667,121 | 0,3691 | 15.778 |
| One Day as a Lion | 177.250 | 634,33-667,79 | 0,3628 | 3.795 |
| Der König der Löwen 2 | 141.250 | 12,14-146,92 | 0,4023 | 270 |
| The Hateful Eight | 316.750 | 637,433-696,500 | 0,3416 | 4.993 |

Die dichte Auswertung meldet in allen Fällen `decoder_seeks=0` und
`decoder_grabs_between_samples=0`.

## 5. Fusion

Phase 2A verwendete drei 1-Sekunden-Samples für den Median und zwei Samples
Persistenz. Auf der 25-fps-Timeline werden dieselben Zeitbreiten deshalb
generisch als 75 Frames Median und 50 Frames Persistenz angewandt; das ist
keine filmspezifische Abstimmung. Die Frame-Grenzbestätigung bleibt bei zwei
Frames. Damit werden Einzelbildfluktuationen unterdrückt, ohne neue Schwellen
zu erfinden.

| Film | PRESENT | ABSENT | CONFLICT | UNKNOWN | bestätigte Zustandswechsel |
| --- | ---: | ---: | ---: | ---: | ---: |
| American Assassin | 31.893 | 56.563 | 126.292 | 2 | 85 |
| Freelance | 134.508 | 51.268 | 28.972 | 2 | 38 |
| One Day as a Lion | 83.441 | 55.480 | 38.327 | 2 | 33 |
| Der König der Löwen 2 | 108.100 | 32.841 | 307 | 2 | 5 |
| The Hateful Eight | 240.975 | 73.565 | 2.208 | 2 | 22 |

Global Reliability annotiert weiterhin nur. Sie löscht keine lokale
Beobachtung. Beide Sensoren und P/A/C/U stehen in jedem Sidecar-Datensatz und
in den Blockdiagnosen getrennt zur Verfügung.

## 6. Umgang mit Comskips globaler `logoPercentage`

Im Baselinepfad bleiben alle drei bestehenden globalen Abschaltstellen
unverändert wirksam. Im experimentellen Pfad dürfen sie LOGO nicht aus
`commDetectMethod` entfernen, solange ein gültiges Sidecar aktiv ist. Der
Comskip-Sensor kann dadurch global low-reliability sein, seine lokalen
Beobachtungen bleiben aber verfügbar. Nach einer optionalen
`--detectmethod`-Angabe wird LOGO im gültigen Hybridmodus erneut strukturell
zugeschaltet.

Das hat bei American Assassin einen realen strukturellen Effekt: Ohne neue
Cutpoint-Art wurden aus den bisherigen übergroßen Showblöcken wieder bestehende
Comskip-Grenzen nahe 37.776/51.274, 86.920/95.496,
126.819/136.310 und 166.846/181.355 nutzbar. Phase 2B konnte diese Wirkung als
reiner Shadow-Score nicht zeigen.

## 7. Exakt entfernte excessive-length-Scorepfade

Nur die beiden Multiplikationen in `WeighBlocks` sind im experimentellen Pfad
mit `!HybridLogoExperimentalActive()` geschützt:

- `length > 2 * min_show_segment_length`: keine Multiplikation mit
  `excessive_length_modifier` mehr, also auch keine quadrierte Wirkung.
- `length > min_show_segment_length`: ebenfalls keine Multiplikation mehr.

Effektiv ist der Faktor in Phase 2C exakt 1,0. Der INI-Wert
`min_show_segment_length=250` bleibt unverändert und wird an allen anderen
Stellen weiterhin verwendet. Blackframe-, AR-, Resolution-, Scene-, Silence-,
Length-Kombinations- und alle übrigen Scoringpfade wurden nicht geändert.

## 8. American Assassin: Baseline gegen Hybrid

| Kennzahl | Baseline | Hybrid |
| --- | ---: | ---: |
| Ground-Truth-Werbebilder | 42.504 | 42.504 |
| korrekt Werbung | 0 | 42.059 |
| verpasst | 42.504 | 445 |
| Ground-Truth-Showframes | 9.411 | 9.411 |
| fälschlich Werbung | 7.739 | 8.032 |

Framegenau pro Werbebereich:

| Ground Truth | Baseline korrekt | Hybrid korrekt | Hybrid verpasst |
| --- | ---: | ---: | ---: |
| 37.700-51.300 | 0 | 13.499 | 102 am Anfang |
| 86.800-95.600 | 0 | 8.577 | 120 am Anfang, 104 am Ende |
| 126.700-136.000 | 0 | 9.182 | 119 am Anfang |
| 167.100-177.900 | 0 | 10.801 | 0 |

Der verbleibende Fehler von 445 Frames ist kein fehlender Werbescore mehr,
sondern die Abweichung vorhandener Blockgrenzen von der Ground Truth. Es fehlt
kein kompletter Bereich. Die erste, dritte und vierte reparierte Einheit hätte
als neuer Hybridblock weiterhin die einfache Längenstrafe erhalten; der zweite
Block ist 343,08 Sekunden lang und hätte keine erhalten. Alle vier lagen in der
Baseline jedoch in 1.370-1.711 Sekunden langen Blöcken mit quadrierter Strafe.

Die bestätigten Showregionen verbessern sich nicht. 8.032/9.411 Showframes
bleiben oder werden Commercial; das sind 293 mehr als in der Baseline. Besonders
179.300-180.200 wächst von 630 auf 901 False-Positive-Frames. Der neue
Commercialblock 199.199-214.746 ist eine große zusätzliche Regression außerhalb
der meisten vorgegebenen Showfenster.

Commercial-Intervalle:

- Baseline: `5650-9085, 16312-17824, 22817-23581, 140826-144569,
  179571-180232, 199458-200288, 214745-214746`
- Hybrid: `5384-9085, 16312-17824, 22624-23581, 37776-51274,
  86920-95496, 126819-136310, 140826-144569, 157155-158021,
  166846-181355, 199199-214746`

## 9. Freelance: Baseline gegen Hybrid

Alle drei bekannten Werbebereiche werden vollständig repariert:

| Ground Truth | Baseline korrekt | Hybrid korrekt | Ursache |
| --- | ---: | ---: | --- |
| 49.414-56.168 | 0/6.755 | 6.755/6.755 | Score 0,04 -> 4,0; 96,52 % ABSENT |
| 90.502-98.346 | 0/7.845 | 7.845/7.845 | Score 0,04 -> 4,0; 76,11 % ABSENT |
| 170.046-176.993 | 0/6.948 | 6.948/6.948 | Score 0,04 -> 4,0; 100 % ABSENT |

Die Logo-Modifier sind jeweils schon vorher und nachher 2,0. Der reparierende
Unterschied ist eindeutig das Auslassen der einfachen Längenmultiplikation
0,01, nicht eine neue Logo-Gewichtung.

Ohne Ground Truth dürfen drei verlorene Baseline-Commercialspannen nicht als
Verbesserung gewertet werden: `4293-4668`, `138549-139155` und
`183686-184472`. Dort ist die Fusion überwiegend PRESENT und der vorhandene
0,01-Logo-present-Modifier macht den umfassenderen Hybridblock zu Show.

Commercial-Intervalle:

- Baseline: `1-4668, 46082-49413, 56169-58282, 89705-90501,
  126884-139155, 176994-184472, 200384-204085, 211312-214746`
- Hybrid: `1-4292, 46082-58282, 89705-98346, 126884-138548,
  170046-183685, 200384-204085, 211312-214746`

## 10. One Day as a Lion: Baseline gegen Hybrid

Der bekannte Werbebereich 25.458-33.804 steigt von 1/8.347 auf
8.347/8.347 korrekt erkannten Frames. Der passende Block 25.459-33.830 ist
100 % ABSENT; der Logo-Modifier bleibt 2,0 und der Score steigt allein durch
das Auslassen der Längenstrafe von 0,04 auf 4,0.

Der Preis ist inakzeptabel:

| bestätigte Showregion | Baseline False Positives | Hybrid False Positives |
| --- | ---: | ---: |
| 1-7.198 | 0 | 7.198 |
| 155.184-177.244 | 12.467 | 22.061 |
| gesamt | 12.467/29.259 | 29.259/29.259 |

In `1-7198` und `167651-177244` melden sowohl der lokale Comskip-Sensor als
auch LogoFinder 0 % Logo und die Fusion 100 % ABSENT. Das ist eine echte lokale
Sensor-/Semantikgrenze: Show ohne erkanntes Logo sieht genauso aus wie ein
langer Werbeblock. Nach Wegfall der einzigen starken Längenschutzregel steigt
der Score jeweils von 0,04 auf 4,0. Bessere P/A/C/U-Aggregation allein kann
diese Bereiche nicht schützen.

Commercial-Intervalle:

- Baseline: `7199-8853, 23240-25458, 71753-78705, 114367-122063,
  150051-167650, 177245-177246`
- Hybrid: `1-8288, 23240-33830, 71753-78705, 114367-122063,
  150051-177246`

## 11. Der König der Löwen 2

Die als gut bewertete Baseline ist nicht invariant:

- `2940-4177` wechselt von Commercial zu Show. Die Fusion ist 98,33 % PRESENT
  und der Logo-present-Modifier 0,01 greift auf einem anders kombinierten
  Hybridblock. Ohne Ground Truth wird dies als mögliche Regression geführt.
- `126222-141244` wechselt von Show zu Commercial. Beide Sensoren und die
  Fusion sind 100 % ABSENT. Der Block ist 600,92 Sekunden lang; die Baseline
  hätte die Längenstrafe quadriert, Hybrid überspringt sie und steigt von
  0,0004 auf 4,0. Dies ist eine klare Kontrollfilm-Regression.

Commercial-Intervalle:

- Baseline: `1-4177, 85066-98695, 141245-141246`
- Hybrid: `1-2939, 85066-98695, 126222-141246`

## 12. The Hateful Eight

Die ersten sechs Baseline-Commercialintervalle bleiben exakt gleich. Am Ende
entsteht jedoch ein neuer Block `289414-316746` statt nur `316708-316746`.
Die geänderte Spanne 289.414-316.707 ist 1.091,76 Sekunden lang, beide Sensoren
sind praktisch 100 % ABSENT, und der Score steigt wegen der ausgelassenen
quadrierten Längenstrafe von 0,0004 auf 4,0. Bei einem als gut bestätigten
Kontrollfilm ist das eine schwere Regression.

## 13. Neue False Positives und potenzielle Regressionen

- One Day: 16.792 zusätzliche bestätigte False-Positive-Showframes;
  insgesamt sind alle 29.259 bestätigten Showframes falsch Commercial.
- American Assassin: 293 zusätzliche False Positives innerhalb der gelieferten
  Show-Ground-Truth und ein sehr großer neuer Endblock.
- König der Löwen 2: neuer Commercial-Endblock mit 15.023 geänderten Frames.
- Hateful Eight: neuer Commercial-Endblock mit 27.294 geänderten Frames.
- Freelance besitzt keine gelieferte Show-Ground-Truth. Drei Baseline-
  Commercialspannen gehen verloren und bleiben deshalb potenzielle neue False
  Negatives statt bestätigter Verbesserungen.

## 14. Verbleibende False Negatives

- American Assassin: nur noch 445 Werbeframes, ausschließlich durch
  Blockgrenzenversatz; kein kompletter Werbebereich fehlt.
- Freelance: 0/21.548 bekannte Werbeframes verpasst.
- One Day: 0/8.347 bekannte Werbeframes verpasst.
- Für die beiden Kontrollfilme wurde keine frameweise Ground Truth geliefert;
  ihre verlorenen oder neuen Intervalle werden nicht semantisch umetikettiert.

## 15. Blockbildungsprobleme

American Assassin beweist, dass das bisherige Hauptproblem tatsächlich die
globale Vernichtung lokaler Logo-Struktur war: Nach dauerhaftem LOGO-Erhalt
werden ohne künstliche Cutpoints alle vier groben Werbeeinheiten wieder
gebildet. Die restlichen 445 Frames sind normale Grenzabweichungen.

Gleichzeitig entstehen aus vorhandenen Comskip-Strukturmechanismen auch neue
Grenzen und Kombinationen außerhalb der Ground Truth. Conflict/Unknown ist bei
der Blockbewertung neutral, kann aber eine bereits von anderen Detektoren
gebildete Commercialstruktur nicht zurücknehmen. Die Endblöcke der beiden
Kontrollfilme sind dagegen keine fehlenden Cutpoints, sondern korrekt
abgegrenzte lange ABSENT-Blöcke, deren Show-Schutz ausschließlich durch die
entfernte Längenstrafe verloren geht.

## 16. Performance

Die Zeiten sind Wall-Clock-Werte aus Metadaten beziehungsweise Comskip-Logs;
die parallele Durchführung beeinflusst sie und war nicht Gegenstand einer
Optimierung.

| Film | Heatmap | Median | alle Frames | Fusion | Baseline Comskip | Hybrid Comskip | Hybrid gesamt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| American Assassin | 1,14 s | 0,44 s | 306,29 s | 24,82 s | 129 s | 195 s | 529,38 s |
| Freelance | 1,91 s | 0,88 s | 327,11 s | 39,62 s | 142 s | 191 s | 563,35 s |
| One Day as a Lion | 1,53 s | 0,64 s | 270,05 s | 37,57 s | 133 s | 170 s | 482,31 s |
| Der König der Löwen 2 | 1,54 s | 0,71 s | 368,72 s | 26,33 s | 82 s | 117 s | 515,97 s |
| The Hateful Eight | 1,58 s | 0,80 s | 589,45 s | 37,40 s | 163 s | 169 s | 800,72 s |

## 17. Regressionstest

- 17 Python-Unit-Tests bestehen.
- Der MSYS-Build besteht; der abschließende `make` meldet, dass alle Targets
  aktuell sind. Bereits vorhandene Compilerwarnungen bleiben unverändert.
- Für alle fünf frischen Baselines sind `.txt`, `.edl`, `.logo.txt` und
  `.logo-raw.csv` per SHA-256 byteidentisch mit den Phase-2B-Baselines.
- Der experimentelle Schalter akzeptiert nur ein gültiges
  `hybrid-logo-v1`-Sidecar. Ohne gültiges Sidecar fällt er auf Baseline zurück.
- Alle Testausgaben liegen isoliert unter
  `D:\PythonProjekte\hybrid_logo_runs\phase2c_end_to_end_20260817`.

Die vollständige maschinenlesbare Auswertung liegt in
`phase2c_evaluation.json`. Die 23 zusammenhängenden Änderungen der finalen
Intervallklasse sind an allen Baseline- und Hybridblockgrenzen in 51 atomare
Blockpaar-Spannen geteilt. Für jede stehen in `phase2c_changed_ranges.csv`
Start/Endframe, PTS, Dauer, Baseline-/Hybridblock, Legacy- und Sidecar-Comskip-
Logoanteil, LogoFinder-Anteil, P/A/C/U, Scores, Modifiern, beiden Längenregeln
und finalen Klassen stehen in `phase2c_changed_ranges.csv` im selben
Verzeichnis. Damit ist jede Änderung reproduzierbar, ohne diese Tabelle im
Bericht zu verkürzen.

## 18. Wichtigste technische Erkenntnisse

1. Die vorhandene Hybrid-Logoerkennung bringt im echten Betrieb einen großen
   Gewinn für American Assassin und bestätigt die Abwesenheitsphasen in den
   reparierten Freelance-/One-Day-Blöcken.
2. Lokale Logo-Evidenz nicht global zu vernichten ist entscheidend: American
   Assassin erhält damit die bisher verlorene Blockstruktur zurück, ohne neue
   Fusions-Cutpoints.
3. Die Längenabwertung vollständig zu entfernen repariert nachweislich alle
   vier bekannten langen Werbe-Scorefehler. Die Modifier ändern sich dort
   nicht; nur 0,01 beziehungsweise 0,0001 entfällt.
4. Freelance wird für alle gelieferten Werbebereiche richtig. One Days Werbung
   wird richtig, aber der Film insgesamt deutlich schlechter.
5. One Days bestätigte Showbereiche sind nicht geschützt. Fusion meldet dort
   belastbar ABSENT; Logoabwesenheit ist also kein hinreichendes Werbesignal.
6. American Assassin verbessert sich von 0 auf 42.059/42.504 bekannte
   Werbeframes, hat aber weiterhin und zusätzlich Show-False-Positives.
7. American Assassin scheitert nicht mehr an vollständiger Blockbildung. Die
   Restabweichung ist ein Grenzproblem, nicht mehr der Phase-2B-Großblockfehler.
8. Beide guten Kontrollfilme werden schlechter, jeweils durch einen großen
   langen ABSENT-Endblock ohne Längenstrafe.
9. Die verbleibenden beziehungsweise neuen Fehler haben teilweise nichts mit
   schlechter Fusion zu tun: Die Fusion ist dort korrekt im Sinne beider
   Sensoren, aber langes logo-loses Showmaterial ist semantisch nicht von
   Werbung unterscheidbar. Das ist eine Commercial-Entscheidungs- und keine
   Logoerkennungsfrage.

## 19. Empfehlung für den nächsten einen Entwicklungsschritt

Als genau nächsten Schritt sollte ein isolierter, zunächst rein diagnostischer
**Long-Block-Safety-Gate** entwickelt werden: Für lange ABSENT-Blöcke muss mit
bereits vorhandener Nicht-Logo-Evidenz geprüft werden, ob die Längenstrafe
entfallen darf. Ziel ist ausschließlich, die vier nachgewiesenen Werbeblöcke
von den nachgewiesenen One-Day-Showblöcken und den beiden Kontrollfilm-
Endblöcken zu trennen. Comskips Logo-Lernverfahren und die nun erfolgreiche
strukturelle LOGO-Verfügbarkeit sollten dabei unverändert bleiben.

Es wird ausdrücklich nicht empfohlen, den hier getesteten globalen
`excessive_length_modifier = 1.0`-Pfad zu übernehmen. In dieser Phase wurde
keine weitere Variante, Schwellenoptimierung oder Parameterreihe gestartet.
