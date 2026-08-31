# Projektübergabe: Comskip V4 Final

Stand: 31. August 2026

Diese Datei ist der verbindliche Wiedereinstieg für spätere Fehleranalysen und Korrekturen. Sie ersetzt nicht den Quellcode oder Git, sondern destilliert die fachlichen Entscheidungen aus dem langen Entwicklungsverlauf.

## 1. Finaler Stand

- Git-Repository: `D:\PythonProjekte\ComSkip Fork`
- Stabiler Branch: `custom`
- Ausgangs-Commit der V4-Entwicklung: `8a3e63a`
- Stabiler Tag: `custom-2026-08-31-v4-stable`
- GitHub-Fork: `https://github.com/cTrares/Comskip`
- Portable Endfassung: `D:\PythonProjekte\ComSkip Fork\dist\ComSkip`

Der V4-Entwicklungsbranch wurde per Fast-Forward in `custom` übernommen. Die
portable Endfassung wurde aus diesem Stand gebaut. `comskip-final.exe` im
portablen Ordner entsprach beim Abschluss exakt dem letzten PyInstaller-Build.

## 2. Unverrückbare Arbeitsgrenzen

1. Ausschließlich unter `D:\PythonProjekte\ComSkip Fork` arbeiten und schreiben.
2. `D:\SysOp\Privat\SOFTWARE\_Medienbearbeitung` ist absolut tabu: nicht lesen, nicht schreiben, nicht prüfen, nichts dorthin kopieren.
3. Dateien aus `C:\Users\XMG Studio\Downloads` dürfen nur als vom Benutzer bereitgestellte Testdaten verwendet werden. Ergebnisse dort nur überschreiben, wenn der Benutzer diesen Testordner ausdrücklich für den betreffenden Lauf freigibt.
4. Film-, Ergebnis- und Teilnehmerdateinamen niemals umbenennen.
5. Portable Ausgaben ausschließlich unter `D:\PythonProjekte\ComSkip Fork\dist\ComSkip` aktualisieren. Die Installation oder Verteilung übernimmt der Benutzer.
6. Keine wiederholten Freigabefragen für normale Arbeiten innerhalb des freigegebenen Projektordners.
7. Ein Batch muss unbeaufsichtigt durchlaufen können. Erforderliche Fallbacks müssen automatisch erfolgen.

## 3. Verarbeitungsprofile

Die Profilwahl ist exklusiv. Ein Film darf genau einem primären Profil zugeordnet werden.

### Öffentlich-rechtlicher Schnellmodus

- Eigenes abgeschlossenes Modul: `public_broadcaster_fast_mode.py`.
- Senderliste ist über `Schnellmodus-Sender.txt` editierbar.
- Ziel sind ausschließlich zwei grobe Randblöcke für Anfang und Ende.
- Keine Suche nach innerer Werbung.
- Bedienhinweis: Filmanfang suchen und `E` drücken; Filmende suchen und `B` drücken.
- Der Schnellmodus darf nicht durch kommerziellen Makromodus, WeDo oder allgemeine Vollanalyse überschrieben werden.
- Realtest „Dann kam Lucy“: erfolgreich, zwei Randblöcke, vollständige TXT, rund 34 Sekunden.

### WeDo Movies

- Aktivierung ausschließlich über den garantiert vorhandenen Dateinamenbestandteil `wedo-movies`.
- Eigenes abgeschlossenes WeDo-Modul: `wedo_movies_detector.py`.
- Interne WeDo-Intervalle sind autoritativ.
- Allgemeine interne Comskip-Blöcke werden verworfen.
- Allgemeine Blöcke dürfen WeDo-Grenzen nicht verlängern.
- Nur disjunkte äußere Crop-Blöcke direkt an den physischen Dateirändern dürfen erhalten bleiben.
- Allgemeine Werbekanten-Nachprüfung ist bei WeDo ausgeschaltet.
- Der intern sichtbare „Comskip-Sensor“ ist ein Messdienst für Logo-Rückkehrpunkte, kein zweiter Entscheidungsweg. Die bisherige Terminalbezeichnung „vollständige Merkmalsanalyse“ ist irreführend, aber die interne WeDo-Ausgabe bleibt autoritativ.

Validierung mit drei WeDo-Filmen gegen manuelle Schnitte:

- 21 von 21 inneren Werbeblöcken gefunden.
- Keine zusätzlichen inneren Blöcke aus einem anderen Prozess.
- 19 von 21 Grenzen innerhalb ±2 Sekunden.
- „Jagd auf einen Unsichtbaren“: letzte Startgrenze 3,04 Sekunden zu früh; akzeptiert.
- „Julia muss sterben“: eine Startgrenze 24,96 Sekunden zu spät; vom Benutzer ausdrücklich akzeptiert und nicht weiter zu optimieren.
- Ein äußerer Ein-Frame-Block am absoluten Dateiende kann vorkommen; er liegt außerhalb des relevanten Filmfensters.

### Kommerzieller Logo-Makromodus

- Eigenes Modul: `commercial_macro_mode.py`.
- Senderliste ist über `Makromodus-Sender.txt` editierbar.
- Strategie: dynamisches Logo aus der jeweiligen Aufnahme lernen, grobe Filmblöcke bilden und nur gefundene Übergangszonen lokal genauer prüfen.
- Falls der Makromodus keinen verwertbaren Schnittblock erzeugt oder abstürzt, startet automatisch die vollständige Analyse. Der Batch wartet nicht auf Benutzereingaben.
- Keine massenhaften orangefarbenen oder Nulllängen-Prüfmarker. Frühere starre Markerabstände waren unbrauchbar und wurden verworfen.

### Allgemeine Vollanalyse

- Nur für Filme, die weder öffentlich-rechtlich, WeDo noch einem aktiven Makromodus-Sender zugeordnet sind, beziehungsweise als automatischer Fallback eines gescheiterten kommerziellen Makromodus.
- `--full-analysis` darf die abgeschlossenen Profile für öffentlich-rechtliche Sender und WeDo nicht umgehen.

## 4. Wichtige abgeschlossene Fehlerkorrekturen

### Stabile Frame-Zuordnung

Der frühere Drei-Frame-Patch war nur Symptombehandlung und wurde entfernt.

Ursache war die nicht inverse Frame–PTS–Frame-Umrechnung beim Laden einer Comskip-TXT. Externe, einsbasierte Framewerte werden jetzt mit `(N - 1) / fps` in PTS zurückübersetzt. Dadurch bleiben sämtliche Schnittgrenzen beim wiederholten Öffnen und Speichern stabil und nicht nur Frame 1.

Relevanter Quellcode: `comskip.c`, Funktion `ExternalFrameToPts` und `InputReffer`.

### Autoritative WeDo-Ausgabe

Die alte Vereinigungslogik konnte trotz richtiger Profilwahl allgemeine interne Blöcke mit WeDo verschmelzen. `apply_wedo_movies_intervals(..., authoritative=True)` verhindert dies jetzt.

### Öffentlich-rechtlicher Absturz bei negativen Kandidaten

Bei ausschließlich negativen Kandidatenwertungen konnte die Nachbarschaftsliste leer werden und `min()` mit `ValueError` abbrechen. Der stärkste Kandidat bleibt jetzt immer als sicherer grober Marker erhalten.

### Korrekte Batch-Erfolgsmeldung

Der Workflow darf `OK` nur anzeigen, wenn tatsächlich eine vollständige Comskip-TXT vorhanden ist. Returncode 0 oder 1 allein genügt nicht mehr. Ohne vollständige TXT erscheint `FEHLER KEINE TXT`.

## 5. Bekannte und akzeptierte Restpunkte

1. Semantisch schwierige Promotion mit sichtbarem Senderlogo, insbesondere Nitro, kann weiterhin zu spät oder zu früh als Filmrückkehr interpretiert werden.
2. Trailer, Eigenwerbung, Countdowns und Programmhinweise können technisch wie Film aussehen.
3. Ein weiterlaufender Film in einem verkleinerten Einblendefenster kann technisch wie Senderpromotion aussehen.
4. Die WeDo-Abweichung von rund 25 Sekunden bei „Julia muss sterben“ ist akzeptiert und soll nicht nachoptimiert werden.
5. Die irreführende WeDo-Phasenbezeichnung ist nur ein Anzeigeproblem. Eine spätere Umbenennung darf die WeDo-Logik nicht verändern.
6. Die Nitro-/API-Erweiterung ist ausdrücklich noch nicht implementiert.

## 6. Mögliche spätere Vision-API

Die Vision-API soll niemals als allgemeiner Scanner über den ganzen Film laufen. Sinnvoll ist sie ausschließlich als seltenes semantisches Schiedsgericht für bereits lokal erkannte Problemzonen.

Geeignete Fälle:

- Senderlogo ist wieder sichtbar, aber es läuft noch Eigenwerbung oder ein Trailer.
- Programmhinweis, Countdown oder „Gleich geht’s weiter“ liegt zwischen Werbung und echtem Film.
- Film oder Abspann läuft in einem verkleinerten Bildfenster weiter.
- Zwei technisch plausible Filmrückkehrpunkte müssen semantisch unterschieden werden.

Vorgesehener Ablauf:

1. Der lokale Makroscanner bleibt unverändert der primäre Scanner.
2. Nur bei widersprüchlichen Signalen wird eine Problemzone geöffnet.
3. Aus dieser Zone werden ungefähr 8–12 chronologische Bilder ausgewählt: sichere Filmreferenz, sichere Werbung, erste vermeintliche Rückkehr, fraglicher Promoabschnitt und spätere Rückkehr.
4. Eine einzige API-Anfrage klassifiziert die Bilder strukturiert als `FILM`, `WERBUNG`, `EIGENWERBUNG`, `PROGRAMMHINWEIS`, `COUNTDOWN`, `FILM_IM_EINBLENDEFENSTER` oder `UNKLAR`.
5. Die API wählt nur die richtige Übergangszone. Die framegenaue Grenze wird weiterhin lokal bestimmt.
6. Timeout, fehlender API-Schlüssel oder `UNKLAR` dürfen den Batch nie abbrechen und keine großflächige automatische Löschung auslösen.
7. Antworten und Bild-Hashes lokal zwischenspeichern, um doppelte Anfragen zu vermeiden.

Offizielle technische Grundlage: `https://developers.openai.com/api/docs/guides/images-vision`

## 7. Zentrale Quelldateien

- `comskip.c`: native Comskip-/GUI-Logik und Frame-Konvertierung.
- `tools/hybrid_logo/comskip_final.py`: exklusive Profilwahl, Fallbacks, Veröffentlichung und Diagnosen.
- `tools/hybrid_logo/public_broadcaster_fast_mode.py`: öffentlich-rechtlicher Schnellmodus.
- `tools/hybrid_logo/wedo_movies_detector.py`: WeDo-Erkennung und autoritative Intervalle.
- `tools/hybrid_logo/commercial_macro_mode.py`: kommerzieller Makromodus.
- `tools/hybrid_logo/commercial_edge_refiner.py`: allgemeine lokale Werbekanten-Nachprüfung außerhalb abgeschotteter Profile.
- `tools/hybrid_logo/multiwindow_logo_experiment.py`: Mehrfenster-Logoanalyse, Sensorfusion und WeDo-Einbindung.
- `dist/ComSkip/_Workflow/Werbung entfernen.py`: Batch-/Prüfworkflow und kompakte Terminalausgabe.
- `tools/hybrid_logo/test_public_broadcaster_fast_mode.py`
- `tools/hybrid_logo/test_wedo_movies_detector.py`
- `tools/hybrid_logo/test_commercial_macro_mode.py`
- `tools/hybrid_logo/test_comskip_final.py`

## 8. Tests und Referenzdaten

Beim Finalisieren liefen 41 relevante Modultests erfolgreich.

Reproduzierbarer Testbefehl aus dem Repository:

```powershell
.\tools\build_windows.ps1 -SkipNative
```

Wichtige manuelle Vergleichsdaten wurden vom Benutzer unter `C:\Users\XMG Studio\Downloads` bereitgestellt, insbesondere:

- `ComSkip Durchlauf.zip`
- `ComSkip Durchlauf vom user korrigiert.zip`

Diese Dateien können später fehlen oder durch neue Testdaten ersetzt werden. Für neue Fehlerfälle immer die aktuelle automatische Ausgabe und die vom Benutzer korrigierte Ausgabe paarweise sichern.

Historischer Analysebericht:

`D:\PythonProjekte\ComSkip Fork\_temp\analysis-new-run-20260830\ANALYSEBERICHT.md`

## 9. Build und portable Veröffentlichung

Der vollständige, von lokalen Fremdprojekten unabhängige Build ist in
`BUILDING.md` dokumentiert. Unter Windows genügt nach Installation der dort
genannten offiziellen Abhängigkeiten:

```powershell
.\tools\build_windows.ps1
```

Danach ausschließlich diese Ziele aktualisieren:

- `D:\PythonProjekte\ComSkip Fork\dist\ComSkip\comskip.exe`
- `D:\PythonProjekte\ComSkip Fork\dist\ComSkip\ComskipGUI.exe`
- `D:\PythonProjekte\ComSkip Fork\dist\ComSkip\comskip-final.exe`
- bei Workflowänderungen `D:\PythonProjekte\ComSkip Fork\dist\ComSkip\_Workflow\Werbung entfernen.py`

Keine automatische Installation außerhalb dieses portablen Ordners.

## 10. Wiedereinstieg in einem neuen Chat

Im neuen Chat zuerst diese Datei vollständig lesen lassen. Anschließend den neuen Fehlerfall konkret benennen und die zugehörigen Videos, automatischen Ergebnisdateien und manuell korrigierten Referenzen bereitstellen.

Empfohlener Starttext:

> Lies zuerst `D:\PythonProjekte\ComSkip Fork\PROJEKTUEBERGABE-V4-FINAL.md` vollständig. Arbeite ausschließlich unter `D:\PythonProjekte\ComSkip Fork`. Der Ausgangsstand ist Git-Tag `custom-2026-08-31-v4-stable`. Analysiere anschließend die von mir genannten neuen Problemfälle gegen meine manuellen Referenzen.

Für eine neue Korrektur vorzugsweise einen neuen Fix-Branch vom Final-Tag anlegen. Den Final-Tag selbst nicht verschieben und die bisherige V4-Fassung nicht überschreiben, bevor der neue Stand validiert ist.
