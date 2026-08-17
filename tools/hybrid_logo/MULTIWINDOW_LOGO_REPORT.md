# Multiwindow-Logo-Experiment

## 1. Git-Zustand

- Branch vor und nach dem Lauf: `feature/hybrid-logo-detection`.
- Vorzustand blieb erhalten: `comskip.c` war geändert, `tools/` war untracked. Kein Reset, Commit, Push, Merge oder Tag.
- LogoFinder blieb unverändert; sein bereits vorhandener Status ist weiterhin `LogoFinder.db-shm`, `LogoFinder.db-wal`, `README.md` und `_cT Verbesserungen.txt` untracked.

## 2. Geänderte Dateien

- `comskip.c`: Opt-ins `--multiwindow-logo-experimental` und `--disable-excessive-length-penalty`; globale Logoquote im Mehrfenstermodus nur Reliability.
- `tools/hybrid_logo/hybrid_logo_analysis.py`: begrenzter Lernbereich für LogoFinder bei vollständiger anschließender Timeline.
- `tools/hybrid_logo/multiwindow_logo_experiment.py`: fünf Lernfenster, Maskenvergleich/-wahl, Fusion, LOGO-/FINAL-STAGE und Einmallauf.
- `tools/hybrid_logo/test_multiwindow_logo_experiment.py`: Sperrzonen-, Masken- und Wiederholungstests.
- Dieser Report.

## 3. Genaue 6-Minuten-Sperrzonen

| Film | Lernbereich | gesperrt am Anfang | gesperrt am Ende |
| --- | --- | --- | --- |
| American Assassin | 360,000–8230,002 s | 0–360 s | 8230,002–8590,002 s |
| Freelance | 360,000–8230,002 s | 0–360 s | 8230,002–8590,002 s |
| One Day as a Lion | 360,000–6730,002 s | 0–360 s | 6730,002–7090,002 s |
| Der König der Löwen 2 | 360,000–5290,017 s | 0–360 s | 5290,017–5650,017 s |
| The Hateful Eight | 360,000–12310,020 s | 0–360 s | 12310,020–12670,020 s |

Die Sperren gelten nur fürs Lernen. Beide Sensoren analysierten danach die vollständige Datei.

## 4. Fünf Comskip-Lernfenster pro Film

Alle Fenster sind 120 s lang, liegen in fünf gleich breiten Zeitstrata des gültigen Mittelbereichs und überlappen nicht.

| Film | Fenster 1 | Fenster 2 | Fenster 3 | Fenster 4 | Fenster 5 |
| --- | --- | --- | --- | --- | --- |
| American Assassin | 1087,000–1207,000 | 2661,001–2781,001 | 4235,001–4355,001 | 5809,001–5929,001 | 7383,002–7503,002 |
| Freelance | 1087,000–1207,000 | 2661,001–2781,001 | 4235,001–4355,001 | 5809,001–5929,001 | 7383,002–7503,002 |
| One Day as a Lion | 937,000–1057,000 | 2211,001–2331,001 | 3485,001–3605,001 | 4759,001–4879,001 | 6033,002–6153,002 |
| Der König der Löwen 2 | 793,002–913,002 | 1779,005–1899,005 | 2765,008–2885,008 | 3751,012–3871,012 | 4737,015–4857,015 |
| The Hateful Eight | 1495,002–1615,002 | 3885,006–4005,006 | 6275,010–6395,010 | 8665,014–8785,014 | 11055,018–11175,018 |

## 5. Kandidatenmasken pro Fenster

Format: `BBox; H/V-Kanten`; `–` bedeutet, dass Comskips bestehende Lernmethode in diesem Fenster keine Maske lieferte.

| Film | W1 | W2 | W3 | W4 | W5 |
| --- | --- | --- | --- | --- | --- |
| American Assassin | 622,68–677,113; 224/467 | 635,73–666,113; 292/439 | 622,70–666,113; 282/449 | 635,73–665,113; 245/400 | 622,68–676,113; 97/400 |
| Freelance | 635,79–666,119; 299/460 | 622,70–665,117; 187/258 | 622,69–665,117; 266/448 | 622,70–665,117; 195/291 | 635,79–665,119; 280/403 |
| One Day as a Lion | – | – | 634,34–666,78; 269/484 | 71,469–131,521; 712/644 | 635,29–665,67; 192/209 |
| Der König der Löwen 2 | 31,22–126,83; 2027/2179 | 31,21–126,83; 1963/2138 | 30,21–127,84; 2398/2518 | – | 30,21–127,84; 2332/2468 |
| The Hateful Eight | – | 641,439–691,492; 964/804 | 641,439–691,492; 965/802 | 641,439–691,492; 952/803 | 641,439–691,492; 953/806 |

## 6. Gewählte Maske und Begründung

| Film | Wahl | Wiederholungsstütze | Wiederholung / lokale Qualität | Grund |
| --- | ---: | ---: | --- | --- |
| American Assassin | W3 | 5/5 | 0,8583 / 0,9977 | bester kombinierter Wert im Fünfer-Cluster |
| Freelance | W3 | 5/5 | 0,8870 / 0,9997 | bester kombinierter Wert im Fünfer-Cluster |
| One Day as a Lion | W3 | 2/5 | 0,6625 / 0,9994 | W3 und W5 wiederholen die obere rechte Struktur; der fremde W4-Kandidat wurde ausgeschlossen |
| Der König der Löwen 2 | W5 | 4/5 | 0,9898 / 0,9988 | bester kombinierter Wert im Vierer-Cluster |
| The Hateful Eight | W3 | 4/5 | 1,0000 / 0,9991 | identische Position und H/V-Struktur im Vierer-Cluster |

Es wurde jeweils genau eine vorhandene Comskip-Maske gewählt; Masken wurden nicht zusammengemischt.

## 7. LogoFinder-Lernbereich

Heatmap, Logo-Region und Medianreferenz verwendeten für jeden Film exakt denselben Bereich aus Punkt 3. Danach lief LogoFinders bestehende lokale Korrelation über alle Frames ab Frame 0.

## 8. Globale Comskip-logoPercentage

| Film | logoPercentage | Sensor am Laufende aktiv |
| --- | ---: | --- |
| American Assassin | 0,643548 | ja |
| Freelance | 0,592791 | ja |
| One Day as a Lion | 0,604100 | ja |
| Der König der Löwen 2 | 0,763202 | ja |
| The Hateful Eight | 0,757781 | ja |

## 9. Hätte Legacy-Comskip das Logo abgeschaltet?

Nein, bei keiner der fünf neu gewählten Masken lag die finale Quote außerhalb des bestehenden Gates. Unabhängig davon zeigen alle fünf Final-Logs, dass der Mehrfenstermodus die Quote nur als Reliability behandelt; kein Log enthält `disabling the use of Logo detection`.

## 10. LOGO-STAGE-Commercialintervalle

- American Assassin: `1-28, 4718-4849, 5367-7633, 37774-46899, 47175-51294, 77012-77063, 86872-95504, 126785-136318, 138171-138274, 167110-177767, 199187-212339, 212445-213893`
- Freelance: `1-3824, 3975-4606, 46083-58247, 89671-90549, 90825-98293, 126840-139110, 169993-184379, 200378-202683, 212192-212304, 213665-213849`
- One Day as a Lion: `1-8199, 23206-28430, 28634-33840, 71705-73328, 73499-73957, 74455-78705, 114314-117105, 117564-122065, 150017-150311, 150665-152119, 153831-154139, 154675-177248`
- Der König der Löwen 2: `1-4157, 85063-98708, 126211-141248`
- The Hateful Eight: `7854-8428, 38024-45683, 45790-47114, 79434-87893, 119023-124699, 124950-127610, 128087-128386, 161319-166969, 167101-168150, 198076-203333, 203504-204764, 253086-259279, 289427-316748`

## 11. FINAL-STAGE-Commercialintervalle

- American Assassin: `37776-51274, 86920-95496, 126819-136310, 167148-177337, 199199-214746`
- Freelance: `1-4668, 46082-58282, 89705-98346, 126884-139155, 170046-183685, 200384-204085, 212825-214746`
- One Day as a Lion: `1-7457, 23240-33830, 71753-78705, 114367-122063, 150051-177246`
- Der König der Löwen 2: `1-2939, 85066-98695, 126222-141246`
- The Hateful Eight: `38019-46671, 79430-87894, 119025-126334, 161321-168151, 198064-204287, 253083-258836, 289414-316746`

## 12. Änderungen durch die übrigen Comskip-Detektoren

| Film | LOGO-STAGE-Werbeframes | FINAL-STAGE-Werbeframes | hinzugefügt | entfernt | netto |
| --- | ---: | ---: | ---: | ---: | ---: |
| American Assassin | 59.256 | 57.306 | 1.233 | 3.183 | −1.950 |
| Freelance | 54.231 | 57.047 | 3.760 | 944 | +2.816 |
| One Day as a Lion | 56.892 | 59.894 | 3.927 | 925 | +3.002 |
| Der König der Löwen 2 | 32.841 | 31.594 | 0 | 1.247 | −1.247 |
| The Hateful Eight | 73.394 | 70.570 | 696 | 3.520 | −2.824 |

Der Experimentlauf entscheidet nicht, ob diese Änderungen visuell besser oder schlechter sind.

## 13. Laufzeit

| Film | Laufzeit |
| --- | ---: |
| American Assassin | 546,8 s gemessene Kernphasen; durch den einmaligen Resume-Randfall ohne gemeinsame Wallclock |
| Freelance | 623,3 s |
| One Day as a Lion | 453,3 s |
| Der König der Löwen 2 | 469,5 s |
| The Hateful Eight | 876,2 s |

Summe der gemessenen Filmphasen: rund 49,5 Minuten. Der Runner-Manifestwert nach dem Resume beträgt 2.535,3 s und enthält die davor bereits abgeschlossenen American-Assassin-Phasen nicht erneut.

## 14. Pfade der zehn Sichtprüfungs-TXTs

- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_22-25_American-Assassin_pro-7_hq_LOGO_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_22-25_American-Assassin_pro-7_hq_FINAL_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_20-15_Freelance_pro-7_hq_LOGO_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_20-15_Freelance_pro-7_hq_FINAL_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-08_00-35_One-Day-As-A-Lion_pro-7_hq_LOGO_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-08_00-35_One-Day-As-A-Lion_pro-7_hq_FINAL_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_18-55_Der-Koenig-Der-Loewen-2-Simbas-Koenigreich_disney-channel_hq_LOGO_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_18-55_Der-Koenig-Der-Loewen-2-Simbas-Koenigreich_disney-channel_hq_FINAL_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_23-22_The-Hateful-Eight_rtlzwei_hq_LOGO_STAGE.txt`
- `D:\PythonProjekte\hybrid_logo_runs\multiwindow_logo_sichtpruefung\2026-08-07_23-22_The-Hateful-Eight_rtlzwei_hq_FINAL_STAGE.txt`
