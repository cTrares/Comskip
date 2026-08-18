# ComSkip – KI-Projektübergabe

**Stand:** 18.08.2026 (finalisierter Runtime-Pfad-/Framearray-Stand)
**Repository:** `D:\PythonProjekte\ComSkip Fork`
**Stabiler Branch:** `custom`
**Finaler technischer Commit:** `0016b5c1ab989648ca75eac02c54ffd3b6dd1dd0`
**Stabiler Tag:** `custom-2026-08-18-4`
**Portable Arbeitsumgebung:** `D:\PythonProjekte\ComSkip Fork\dist\ComSkip`
**`comskip.exe` SHA-256:** `49BDDC4A9EE48F2629E659E1D25CE5A28B508A42CBE9593CA30E3C72666616D5`
**`ComskipGUI.exe` SHA-256:** `53AADCF4BB86EFB83593128B70AC5CA4176E2DB0CF59D25A6B0579FA6E5061A8`
**`comskip-final.exe` SHA-256:** `A68009AC279C6A743DBD558EFED9996A13132B32BA29FF2AC672D0F718FF4B2E`
**Aktuelle `Werbung entfernen.py` SHA-256:** `652B1FE9E96E9792D92E7B536B780260354C86F06ECC9E1BBA9CCE21CE8CCF8E`
**Python-BUILD_ID:** `2026-08-18-BATCH-ABORT-PROCESS-TREE`
**Git-Status:** `custom` und `origin/custom` synchron, Working Tree sauber

---

## ANWEISUNG FÜR EINEN NEUEN KI-ASSISTENTEN

Diese Datei ist die Projektübergabe des Benutzers. Sie soll in einem neuen Chat den bisherigen Projektkontext ersetzen.

Nach dem Einlesen dieser Datei:

1. Den Benutzer nicht erneut nach Grundlagen fragen, die hier dokumentiert sind.
2. Die Rolle des technischen Entwicklungsleiters übernehmen.
3. Der Benutzer ist technischer Laie und nutzt Codex als ausführenden Entwickler.
4. Technische Entscheidungen nicht auf Basis einer laienhaften Problembeschreibung erraten.
5. Bei konkreten Änderungen zuerst den tatsächlichen aktuellen Projektzustand von Codex prüfen lassen.
6. Copy/Paste-fertige, technisch präzise Codex-Aufträge formulieren.
7. Möglichst zuerst read-only analysieren, dann eine kleine Änderung umsetzen lassen.
8. `custom` bis nach einem praktischen Test durch den Benutzer stabil lassen.
9. Python-Workflow und Git-/C-Projekt strikt getrennt behandeln.
10. Nach Codex-Berichten das Ergebnis bewerten und den nächsten Schritt vorgeben.
11. Nicht annehmen, dass Commit, Tag oder SHA-Werte nach dem oben genannten Stand noch aktuell sind; bei neuen Änderungen verifizieren lassen.
12. Keine unnötige PR-, Review- oder Infrastruktur-Komplexität einführen.

Der Benutzer möchte nicht selbst Git-Kommandos, C-Quellcode oder Builddetails beurteilen müssen. Die KI soll die technische Führung übernehmen und Codex entsprechend anweisen.

---

# 1. Projekt in einem Satz

Das Projekt ist ein persönlicher Comskip-Fork mit angepasster ComskipGUI und einem lokalen Python-Workflow, der aus automatischer Werbeerkennung, visueller Korrektur und abschließendem Avidemux-Crop einen kontrollierten Videoschnitt-Workflow bildet.

---

# 2. Rollen der Komponenten

## Comskip

Im normalen Portable-Workflow startet `comskip-final.exe` die vollständige Analyse. Es koordiniert das mehrteilige Logo-Lernen und ruft den nativen Kern `comskip.exe` für dessen bewährte lokale und blockbasierte Erkennung auf.

Es erzeugt unter anderem die Comskip-TXT, Logdateien, EDL und Logo-Daten.

## ComskipGUI

`ComskipGUI.exe` dient zur visuellen Prüfung und Korrektur der von Comskip erkannten Werbeblöcke.

Hier werden nur Werbeblöcke bearbeitet.

Automatisch erkannte Commercial-Bereiche am Dateianfang oder Dateiende dürfen vom CROP-Workflow berücksichtigt werden. Der tatsächliche Filmanfang und das tatsächliche Filmende werden trotzdem immer in Avidemux visuell kontrolliert und bei Bedarf manuell nachgecroppt.

## Python-Workflow

`_Workflow\Werbung entfernen.py` verbindet Analyse über `comskip-final.exe`, ComskipGUI-Prüfung und Avidemux-Vorbereitung.

Diese Datei ist ein persönlicher lokaler Workflow und gehört nicht zum Git-Repository.

## Avidemux

Avidemux übernimmt:

- Kontrolle der automatisch entfernten inneren Werbeblöcke,
- finalen Filmanfang,
- finales Filmende,
- Speichern per Direct Stream Copy.

**Grundregel:** Bestätigte Commercial-Bereiche am Dateianfang oder Dateiende dürfen im CROP-Projekt technisch schnittsicher berücksichtigt werden. Der tatsächliche Filmanfang und das tatsächliche Filmende werden anschließend weiterhin in Avidemux visuell kontrolliert und bei Bedarf im Copy-Modus manuell auf geeigneten Keyframes nachgecroppt.

---

# 3. Dokumentation, die bewusst erhalten wird

Es gibt drei aktive maßgebliche Dokumente:

## `ComSkip Manual.html`

Bedienungsanleitung für den Benutzer.

Enthält Tasten, praktische Arbeitsschritte, Entscheidung C/M/Q, E-Nachprüfung und Avidemux-Bedienung.

## `ComSkip_KI_Projektuebergabe.md`

Diese Datei.

Sie ist das technische Projektgedächtnis für einen neuen KI-Assistenten.

## `ComSkip_KI_Projektuebergabe.html`

Renderbare HTML-Fassung der technischen Projektübergabe.

DOCX-Dateien sind keine aktive Dokumentation. Frühere Dokumente wie eine separate Workflow-Beschreibung oder Projekt-Kurzbeschreibung sind nicht erforderlich, wenn Manual und diese Übergabe aktuell gehalten werden.

---

# 4. Repository und Git

Repository:

`D:\PythonProjekte\ComSkip Fork`

Stabiler Hauptbranch:

`custom`

Aktueller dokumentierter technischer Stand:

`0016b5c1ab989648ca75eac02c54ffd3b6dd1dd0`

Aktueller stabiler Tag:

`custom-2026-08-18-4`

Vorherige stabile Tags:

- `custom-2026-08-18-3` → `a08d0110b9ba9e60cdc50bb93805892740aa4503` (unverändert)
- `custom-2026-08-18-2` → `79f1eb75844ffb37d7ac0e72914f39a1fa5799f8`
- `custom-2026-08-18` → älterer stabiler Stand
- `custom-2026-08-17` → `9222f21f455ce0fafbe9667b367e377455c6f1cd`
- `custom-2026-08-17-2` → `49c46cae0b3cdff5669ab03330bcb167d40144b2`
- `custom-2026-08-17-3` → `1d58e8f65cc4c821d7c546064377db6dd9e38761`

Zum dokumentierten Stand sind `custom` und `origin/custom` synchron und der Working Tree ist sauber.

---

# 5. Git-Konvention des Projekts

Für Änderungen am Comskip-/ComskipGUI-C-Code gilt normalerweise:

1. Tatsächlichen Stand analysieren.
2. Neue Änderung auf Feature-Branch entwickeln.
3. `custom` zunächst unverändert lassen.
4. Normal bauen.
5. Nur die tatsächlich benötigte Testdatei nach `dist\ComSkip` deployen.
6. Benutzer testet praktisch.
7. Erst nach ausdrücklichem Erfolg kontrolliert nach `custom` integrieren.
8. Fast-Forward bevorzugen, wenn die Branch-Historie das sinnvoll erlaubt; bei einem abgeschlossenen größeren Feature ist ein klarer Merge-Commit zulässig.
9. `custom` zu `origin/custom` pushen.
10. Stabilen Tag setzen.
11. Feature-Branch darf lokal bestehen bleiben.
12. Keine Pull Requests für diesen persönlichen Workflow, solange sie keinen konkreten Nutzen haben.

Performance ist eine harte Anforderung. Keine Navigation künstlich drosseln.

---

# 6. GitHub versus lokale Portable-Umgebung

Der GitHub-/Git-Stand enthält das eigentliche C-/GUI-Projekt.

Die vollständige persönliche Portable-Umgebung befindet sich dagegen lokal unter:

`D:\PythonProjekte\ComSkip Fork\dist\ComSkip`

`dist` ist bewusst nicht Git-getrackt.

Der Ausschluss erfolgt lokal über Git-Exclude/Trackingregeln; der Ordner soll nicht versehentlich in Git aufgenommen werden.

Folge:

Ein sauberer GitHub-Stand sichert **nicht** automatisch:

- die komplette Portable-Umgebung,
- `_Workflow`,
- `Werbung entfernen.py`,
- persönliche Start-BATs,
- lokale Zusammenstellung der EXEs und DLLs.

Deshalb wird `dist\ComSkip` separat als Backup gesichert.

---

# 7. Portable ComSkip-Umgebung

Maßgeblicher Ordner:

`D:\PythonProjekte\ComSkip Fork\dist\ComSkip`

Wichtige Dateien:

- `comskip-final.exe`
- `comskip.exe`
- `ComskipGUI.exe`
- `ffmpeg.exe` und `ffprobe.exe`
- DLLs
- `comskip.ini`
- `comskip.dictionary`
- `_Workflow\...`

## EXE-Namen nicht verwechseln

### `comskip-final.exe`

Normales Benutzer-Analyseprogramm. Es enthält den internen zweiten Logosensor einschließlich OpenCV/NumPy und koordiniert die fünf Lernfenster, den ersten Comskip-Videoscan, Fusion und den finalen Comskip-Re-Score aus der Framearray-CSV.

### `comskip.exe`

Nativer Comskip-Kern mit Terminalausgabe. Er wird im finalen Workflow durch `comskip-final.exe` aufgerufen.

### `ComskipGUI.exe`

Aktuell vom persönlichen Workflow verwendete GUI.

`Werbung entfernen.py` startet genau diese Datei.

### Frühere portable `comskip-gui.exe`

Die alte Vergleichs- bzw. Rückfallkopie wurde nach Prüfung aller lokalen Referenzen entfernt. Der aktuelle Python-Workflow startet ausschließlich `ComskipGUI.exe`.

---

# 8. GUI-Build und Portable-Deploy

Der normale Build im Repository erzeugt unter anderem:

- `comskip.exe`
- `comskip-gui.exe`

Für einen GUI-Test wird die gebaute Repository-Datei:

`repo\comskip-gui.exe`

nach:

`dist\ComSkip\ComskipGUI.exe`

kopiert/umbenannt.

Eine separate portable `comskip-gui.exe` ist nicht mehr vorhanden.

Keine dritte Backup-EXE erzeugen.

Aktuell finale `ComskipGUI.exe`:

SHA-256:

`53AADCF4BB86EFB83593128B70AC5CA4176E2DB0CF59D25A6B0579FA6E5061A8`

---

# 9. Persönlicher Python-Workflow

Maßgebliche Datei:

`D:\PythonProjekte\ComSkip Fork\dist\ComSkip\_Workflow\Werbung entfernen.py`

Diese Datei ist die autoritative aktuelle Workflow-Version.

Nicht nach einer angeblich anderen Source-Kopie suchen, solange der Benutzer nichts anderes sagt.

Sie ist nicht Git-getrackt.

Aktueller dokumentierter SHA-256:

`652B1FE9E96E9792D92E7B536B780260354C86F06ECC9E1BBA9CCE21CE8CCF8E`

Statischer Buildstring:

`2026-08-18-BATCH-ABORT-PROCESS-TREE`

Dieser Buildstring ist **nicht** die GUI-Version und wird nicht automatisch bei jeder Workflow-Korrektur geändert.

---

# 10. Relative Pfadauflösung des Workflows

Der Workflow liegt unter `_Workflow` und verwendet den Parent-Ordner als Portable-ComSkip-Verzeichnis.

Sinngemäß:

```python
workflow_dir = Path(__file__).resolve().parent
comskip_dir = workflow_dir.parent
comskip_core = comskip_dir / "comskip.exe"
comskip_final = comskip_dir / "comskip-final.exe"
comskip = comskip_final if comskip_final.exists() else comskip_core
gui = comskip_dir / "ComskipGUI.exe"
```

Darum kann der gesamte `ComSkip`-Ordner innerhalb des PCs verschoben oder umbenannt werden, solange die relative Struktur erhalten bleibt.

## Portable-Basis von `comskip-final.exe`

Im Frozen-/EXE-Betrieb ist der Ordner der tatsächlich gestarteten `comskip-final.exe` die Portable-Basis. Die benötigten Geschwisterdateien `comskip.exe`, `comskip.ini`, `ffmpeg.exe` und `ffprobe.exe` werden ausschließlich relativ zu diesem Ordner aufgelöst. Es gibt dabei keinen PATH-Fallback und keine feste Bindung an `D:\PythonProjekte`, `D:\SysOp` oder einen anderen Installationspfad. Wird der komplette Ordner verschoben oder auf einen anderen PC kopiert, verwendet die EXE automatisch ihre Geschwisterdateien am neuen Ort.

Der Entwicklungsbetrieb darf weiterhin eine geeignete Entwicklungsauflösung verwenden. `sys._MEIPASS` bezeichnet den Entpackort gebündelter Ressourcen und ist nicht mit dem Portable-Anwendungsordner gleichzusetzen.

---

# 11. Start-BAT

Maßgeblicher Starter:

`_Workflow\Werbung entfernen Start.bat`

Er startet `Werbung entfernen.py` aus seinem eigenen Ordner, bevorzugt über `py -3`, sonst über `python`.

Für die neue E-Funktion war keine Änderung an dieser BAT erforderlich.

---

# 12. Aktuelles Hauptmenü des Python-Workflows

Das praktisch getestete Hauptmenü lautet:

```text
A - Analysieren und danach offene Filme prüfen
N - Nur analysieren
P - Nur offene Filme prüfen / Prüfung fortsetzen
E - Film auswählen / erneut prüfen
Q - Beenden
```

## A

Analysiert fehlende Filme und prüft danach offene Filme.

## N

Analysiert fehlende Filme und beendet danach.

## P

Überspringt Analyse und prüft nur offene Filme.

## E

Gezielte Auswahl eines beliebigen vorhandenen MP4-Films, unabhängig vom bisherigen Bearbeitungsstatus.

## Q

Beendet das Hauptprogramm.

## Laufende Analyse anhalten oder abbrechen

- `B` setzt `stop_after_current`: Der aktuelle Film wird fertig analysiert, danach endet der Batch und der Workflow kehrt ins Hauptmenü zurück.
- `X` bricht die aktuelle Analyse sofort ab, beendet gezielt deren Prozessbaum, startet keinen nächsten Film und kehrt ins Hauptmenü zurück.
- `Strg+C` verwendet während der Analyse denselben sicheren Abbruchpfad wie `X`.

Jeder Analysejob läuft in einem Windows Job Object mit `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; der Sofortabbruch verwendet gezielt `TerminateJobObject`. Gleichnamige fremde Prozesse werden nicht pauschal beendet. Mehrfaches `Strg+C` wurde ohne Traceback getestet, ein fremder Kontrollprozess blieb unberührt. Ein abgebrochener Film gilt nicht als vollständig analysiert, bestehende gültige Benutzerergebnisse bleiben geschützt und der Film kann später erneut analysiert werden.

---

# 13. Filmstatus im E-Menü

E liest bei jeder Anzeige den aktuellen MP4-Bestand im normalen Downloads-Ordner neu ein und zeigt eine nummerierte Liste.

Mögliche Status:

- `CROP`
- `MANUELL`
- `OFFEN`
- `NICHT ANALYSIERT`
- `KONFLIKT`

`0` führt aus der E-Liste zurück zum Hauptmenü.

Start-BAT-Dateien sind **keine** fachlichen Entscheidungsmarker.

## CROP

Aktuelle oder historische CROP-Entscheidung vorhanden.

Aktueller Marker ist insbesondere `_Avidemux_CROP.py`.

Historische `_Avidemux.py` kann ebenfalls als alte CROP-Entscheidung erkannt werden.

## MANUELL

`_Comskip_MANUELL.txt` vorhanden.

## OFFEN

Vollständige Comskip-TXT vorhanden, aber noch keine Entscheidung CROP/MANUELL.

## NICHT ANALYSIERT

Keine vollständige Comskip-TXT vorhanden.

## KONFLIKT

CROP- und MANUELL-Entscheidung gleichzeitig vorhanden.

Keinen automatischen Default verwenden; Konflikt ausdrücklich behandeln.

---

# 14. E – Film auswählen / erneut prüfen

E ist nicht nur für bereits bearbeitete Filme gedacht.

Es kann **jeder** Film aus dem normalen Downloads-Bestand ausgewählt werden.

## Noch nicht analysierter Film

Der bestehende normale Einzelanalyseweg wird verwendet.

Nach erfolgreicher Analyse öffnet sich der Film direkt in ComskipGUI.

Es gibt keine zweite parallele Analysemechanik.

## Bereits analysierter Film

Die vorhandene TXT wird direkt in ComskipGUI geöffnet.

Eine CROP-/MANUELL-Entscheidung verhindert die erneute Prüfung ausdrücklich nicht.

---

# 15. E – erneute Entscheidung nach ComskipGUI

Bei einem bereits entschiedenen Film wird die vorherige Entscheidung vor dem GUI-Aufruf gemerkt.

## Enter bei vorherigem CROP

CROP beibehalten und CROP-Dateien **immer** neu erzeugen.

Dies gilt auch bei byteidentischer TXT.

## Enter bei vorherigem MANUELL

MANUELL beibehalten und MANUELL-Dateien **immer** neu erzeugen.

Dies gilt auch bei byteidentischer TXT.

Der Sinn ist wichtig:

Alte Filme können dadurch später mit einer verbesserten Generatorlogik erneut aufgebaut werden, ohne dass die Comskip-TXT inhaltlich geändert werden muss.

## C

CROP wählen bzw. bestätigen und aktuellen CROP-Artefaktsatz erzeugen.

## M

MANUELL wählen bzw. bestätigen und aktuellen MANUELL-Artefaktsatz erzeugen.

---

# 16. E – Q-Semantik

Dieser Punkt wurde praktisch getestet und nachträglich korrigiert.

Q bedeutet im E-Modus:

**„Entscheidung beibehalten und zurück.“**

## Vorher CROP oder MANUELL, TXT unverändert

Keine Neugenerierung.

Keine Bereinigung.

Entscheidung bleibt wie sie war.

Rückkehr zur E-Auswahlliste.

## Vorher CROP, TXT wurde in ComskipGUI gespeichert und byteweise geändert

CROP bleibt die Entscheidung.

CROP-PY und CROP-Start-BAT werden automatisch neu erzeugt, damit sie wieder zur geänderten TXT passen.

## Vorher MANUELL, TXT wurde gespeichert und byteweise geändert

MANUELL bleibt die Entscheidung.

MANUELL-Marker und MANUELL-Start-BAT werden automatisch neu geschrieben.

## Vorher OFFEN, TXT geändert, danach Q

Film bleibt OFFEN.

Die gespeicherte TXT-Änderung bleibt selbstverständlich erhalten.

Es wird weder CROP noch MANUELL erzeugt.

Dies wurde praktisch erfolgreich getestet.

## KONFLIKT

Kein automatischer Default.

---

# 17. C – Crop

C wird verwendet, wenn echte Werbeblöcke automatisch entfernt werden sollen. Das können Blöcke innerhalb des Films sowie bestätigte Commercial-Bereiche am Dateianfang oder Dateiende sein.

Erzeugt:

```text
<Film>_Avidemux_CROP.py
<Film>_Avidemux_CROP_Start.bat
```

Das erzeugte Avidemux-Projekt lädt die Original-MP4, baut aber eine Arbeits-Timeline aus den zu behaltenden Filmsegmenten auf.

Die Original-MP4 wird dadurch noch nicht verändert.

---

# 18. M – Manuell

M bedeutet:

**Keine automatischen Comskip-Werbeschnitte übernehmen.**

Typische Fälle:

- öffentlich-rechtlicher Film ohne Werbung,
- werbefreie Privatausstrahlung,
- Comskip-Erkennung unbrauchbar,
- allgemein keine automatischen inneren Werbeschnitte gewünscht.

M erzeugt aktuell immer:

```text
<Film>_Comskip_MANUELL.txt
<Film>_Avidemux_MANUELL_Start.bat
```

Die MANUELL-Start-BAT öffnet ausschließlich die Original-MP4 in Avidemux.

Kein Avidemux-Projekt.

Keine Segmentliste.

Keine Comskip-Schnittmarken.

Keine automatische Werbung wird entfernt.

Der verifizierte Aufruf ist sinngemäß:

```bat
start "" "%AVIDEMUX%" --load "%VIDEO%"
```

Die BAT verwendet dieselbe robuste Avidemux-Suche wie der CROP-Starter.

---

# 19. Wechsel zwischen CROP und MANUELL

Widersprüchliche Entscheidungsartefakte sollen nicht zurückbleiben.

## CROP → MANUELL

Zuerst neue MANUELL-Artefakte erfolgreich schreiben.

Danach alte CROP-Artefakte entfernen, einschließlich historischer Varianten, soweit vorhanden.

## MANUELL → CROP

Zuerst neue CROP-Artefakte erfolgreich schreiben.

Danach MANUELL-Artefakte entfernen.

Historische `_Avidemux.py` / `_Avidemux_Start.bat` werden bei aktueller CROP-Neuerzeugung ebenfalls bereinigt.

Wichtiges Sicherheitsprinzip:

Nicht zuerst die bisherige funktionierende Entscheidung löschen und erst danach neue Dateien erzeugen.

---

# 20. Keine automatische Massenmigration alter MANUELL-Filme

Alte MANUELL-Filme, die vor Einführung der neuen Funktion noch keine `_Avidemux_MANUELL_Start.bat` besitzen, werden nicht automatisch beim Programmstart migriert.

Sie erhalten die neue BAT, wenn sie über E erneut geöffnet und MANUELL per Enter oder M bestätigt werden.

---

# 21. Praktische Entscheidungsregel C versus M

Es gibt im Workflow praktisch keinen Fall „Film ist schon komplett fertig“.

Mindestens Filmanfang und Filmende werden später in Avidemux geprüft/gecroppt.

## M verwenden

Wenn keine automatischen inneren Werbeschnitte gewünscht sind.

Die von Comskip erkannten Blöcke sind dann für den späteren Avidemux-Start irrelevant.

## C verwenden

Wenn echte Werbeblöcke automatisch entfernt werden sollen – innerhalb des Films oder als bestätigte Commercial-Bereiche am Dateianfang beziehungsweise Dateiende.

Sehr wichtig:

Comskip-Blöcke am Anfang oder Ende nur dann mit `D` löschen, wenn sie falsch erkannt wurden oder ausdrücklich nicht automatisch berücksichtigt werden sollen.

Die echten Werbeblöcke stehen lassen.

Dann speichern und C wählen.

Grund:

Die aktuelle Generatorlogik verarbeitet bestätigte Vor-/Nachlaufblöcke technisch schnittsicher. Das ersetzt nicht die spätere visuelle Kontrolle und den bei Bedarf manuellen Anfangs-/Endcrop in Avidemux; technische Schnittsicherheit ist keine Garantie für inhaltlich perfekte automatische Erkennung.

---

# 22. ComskipGUI – wichtigste Bedienlogik

Wichtige Tasten:

- `N` → vorherige Werbeblockgrenze
- `M` → nächste Werbeblockgrenze
- Pfeil runter → +1 Sekunde, zeitlich vorwärts
- Pfeil hoch → -1 Sekunde, zeitlich rückwärts
- Bild runter / Page Down → +20 Sekunden, zeitlich vorwärts
- Bild hoch / Page Up → -20 Sekunden, zeitlich rückwärts
- Rechts/Links → framegenau
- `B` → Blockanfang setzen
- `E` → Blockende setzen
- `D` → Block löschen
- `I` → neutralen Ein-Frame-Anker setzen
- `Strg+Z` → Undo, bis zu 10 Schritte
- `Z/U` → Timeline-Zoom hinein/heraus
- `W` → sofort speichern

Beim Schließen mit Esc, X oder Alt+F4 fragt ComskipGUI bei ungespeicherten Änderungen nach:

- Ja → speichern
- Nein → verwerfen
- Abbrechen → weiterarbeiten

---

# 23. ComskipGUI – Fenster und Layout

Der stabile Custom-Stand enthält unter anderem:

- Start maximiert.
- Timeline nutzt die aktuelle verfügbare Clientbreite.
- Oberhalb des Videos ist der Timeline-/Info-Bereich reserviert.
- Video wird proportional verkleinert.
- Kein Upscaling.
- Video horizontal und vertikal zentriert.
- Resize/Restore berechnet Layout neu.
- Sehr kleine Zielgrößen werden sicher behandelt.
- `MIN_VIDEO_DISPLAY_SIZE` ist 16.

---

# 24. ComskipGUI – Timeline-Scrubbing

Praktisch gewünschtes Verhalten:

- Drag beginnt auf der Timeline → Scrubbing aktiv.
- Maus darf danach die Timeline vertikal verlassen; Drag bleibt aktiv.
- Dragbeginn im Video startet kein Timeline-Scrubbing.

Diese Eigenschaften dürfen bei späteren Änderungen nicht versehentlich verloren gehen.

---

# 25. ComskipGUI – Double Buffering

Schnelle Navigation war früher sichtbar flackernd.

Performance durfte nicht durch Drosselung erkauft werden.

Der stabile Fix verwendet:

- persistenten clientgroßen GDI-Backbuffer,
- vollständige Komposition offscreen,
- genau einen `BitBlt` zum sichtbaren Window-DC pro normalem Render,
- `WM_PAINT` präsentiert nur den letzten gültigen Backbuffer,
- kein Decoder-/Rebuild-Aufruf in `WM_PAINT`,
- `WM_ERASEBKGND` unterdrückt unnötiges Löschen bei gültigem Backbuffer,
- Backbuffer-Neuanlage nur bei Resize,
- keine Timer,
- kein Debounce,
- kein Throttling,
- keine absichtlich verworfenen Eingaben.

Feature-Commit des Double-Buffering-Fixes:

`9222f21f455ce0fafbe9667b367e377455c6f1cd`

---

# 26. Graph-/Marker-Cleanup

Ein alter Upstream-Fehler ließ bei Navigation rote Markerreste im oberen schwarzen Timeline-Bereich stehen.

Ursache:

Der Review-Graph besitzt zusätzliche 32 Pixel Höhe, wurde aber an zwei Stellen nur mit `owidth * oheight * 3` gelöscht.

Fix:

Vollständigen Graph einschließlich `barh=32` löschen.

Commit:

`49c46cae0b3cdff5669ab03330bcb167d40144b2`

Damit verschwanden die alten roten Markerreste.

---

# 27. Timeline-Visibility-Fix

Sehr kurze echte Commercial-Blöcke konnten in der alten Darstellung vollständig unsichtbar werden.

Beispiel aus `Man of Steel`:

`252217–252246`

Der Block war real in TXT/Log vorhanden und mit M anspringbar, aber auf der Timeline nicht sichtbar.

Ursache:

Die alte Timeline klassifizierte jede Pixelspalte nur anhand eines einzigen Stichproben-Frames.

Kurze Blöcke konnten zwischen diesen Stützpunkten liegen.

Der aktuelle stabile Fix:

- prüft das vollständige Frameintervall jeder Timeline-Spalte auf Überlappung mit Commercial-Blöcken,
- verwendet 64-Bit-Zwischenwerte für Mapping-Berechnungen,
- garantiert Sichtbarkeit sehr kurzer Commercial-Aktivität,
- verwendet zwei Clientpixel Randreserve links und rechts,
- stimmt Frame↔X- und Mausmapping auf denselben inneren Bereich ab,
- zeichnet Marker nach den Balken,
- begrenzt Marker sauber auf gültige Bereiche,
- verändert keine fachlichen `reffer[]`-Grenzen.

Commit:

`1d58e8f65cc4c821d7c546064377db6dd9e38761`

Tag:

`custom-2026-08-17-3`

Praktischer Test: vollständig erfolgreich.

---

# 28. Bekannte blaue gestrichelte Linie

Bei bestimmten No-Commercial-Fällen kann eine alte blaue punktierte/gestrichelte Linie in der Timeline erscheinen.

Sie wurde untersucht.

Sie stammt aus altem Upstream-Verhalten und ist für den Benutzer kein relevantes Problem.

Nicht erneut als Double-Buffering-Regression behandeln, solange kein neues Verhalten hinzukommt.

---

# 29. No-Commercial und EDL

Bei einem Lauf mit wirklich null erkannten Werbeblöcken kann eine leere EDL korrekt sein.

Die EDL wird beim Öffnen angelegt und nur mit echten Commercial-Blöcken beschrieben.

Eine leere EDL allein beweist jedoch nicht, dass der Lauf vollständig erfolgreich abgeschlossen wurde; dafür ist gegebenenfalls das vollständige Log maßgeblich.

ComskipGUI verwendet im relevanten Reviewpfad die Comskip-TXT bzw. `reffer[]`, nicht die EDL.

Die EDL beeinflusst daher die GUI-Reviewliste nicht direkt.

---

# 30. Technischer Comskip-End-Sentinel

Comskip kann am Ende einer TXT einen technischen Eintrag erzeugen, der wie ein Werbeblock aussieht.

Exakte erkannte Regel:

```text
last_end == last_start + 1
und
last_end == total_frames
```

Dieser Eintrag ist kein echter Commercial.

Der Python-Workflow entfernt genau diesen Sentinel.

Wichtig:

- keine pauschale Entfernung kurzer Blöcke,
- Sentinel vor Clamping, Sortierung und Merge entfernen,
- EDL nicht zur Entscheidung verwenden,
- echte kurze Commercial-Blöcke bleiben erhalten.

Der Sentinel-Fix wurde praktisch getestet.

---

# 31. `is_complete_comskip_txt()` bewusst nicht anfassen

Die Funktion prüft derzeit im Wesentlichen, ob die erste Zeile mit `FILE PROCESSING COMPLETE` beginnt.

Eine theoretische Robustheitsfrage wurde diskutiert.

Der Benutzer hat ausdrücklich entschieden, dass dieses Thema derzeit nicht relevant ist.

Nicht ungefragt erneut öffnen oder ändern.

---

# 32. Avidemux-CROP-Projekt

Nach C wird ein Avidemux-Projekt erzeugt.

Vorher werden überlappende bzw. direkt aneinandergrenzende Werbeblöcke im Python-Workflow zusammengeführt.

Aus den verbleibenden Bereichen entstehen die zu behaltenden Filmsegmente.

Die Comskip-TXT verwendet 1-basierte, inklusive Framegrenzen. Frame 0 ist dort kein eigener Videoframe. Die Zahl in `FILE PROCESSING COMPLETE ... FRAMES` ist der höchste gültige Comskip-Frameindex; wegen der 1-basierten Zählung ist sie zugleich die Zahl der von Comskip adressierten Frames. Ein Intervall `a–b` entfernt daher die Originalframes `a` bis `b` einschließlich. In der 0-basierten Avidemux-Zeitachse entspricht dies `[a-1,b)`: Das vorherige Keep-Segment endet exklusiv bei `a-1`, das nächste beginnt beim Avidemux-Frameindex `b`, also beim ursprünglichen Comskip-Frame `b+1`. Ein defensiv eingelesener Startwert 0 wird wie der erste gültige Frame behandelt.

Avidemux-Segmente werden als Start plus Dauer und damit mit exklusivem End-PTS aufgebaut. Reicht ein Keep-Segment bis zum Dateiende, verwendet das Projekt das tatsächliche Avidemux-Referenzende statt einer aus der Comskip-Kopfzahl hochgerechneten Grenze. Damit bleiben auch wenige Decoder-/Reorder-Frames erhalten, welche hinter dem höchsten von Comskip gemeldeten Frame liegen können.

Für jeden Wiedereinstieg nach Werbung fordert das Projekt ausdrücklich den vorherigen Keyframe über:

`Editor.getPrevKFramePts(...)`

Der neue Filmabschnitt kann deshalb einige Sekunden früher beginnen und eventuell einen kleinen Werberest enthalten.

Das ist gewollt.

Sauberer Copy-Wiedereinstieg hat Vorrang vor einem optisch exakt an der Commercial-Grenze liegenden Start.

Alle benötigten Keyframes werden ermittelt, solange die ursprüngliche Editor-Timeline noch vorhanden ist, und erst danach werden die Avidemux-Segmente neu aufgebaut. `getPrevKFramePts(...)` liefert lineare Timeline-Zeit, `addSegment(...)` erwartet dagegen Referenz-PTS; der Generator rechnet deshalb den von Avidemux gemeldeten Segment-PTS-Offset ausdrücklich ab und wieder hinzu. Ein bereits exakt getroffener Keyframe bleibt durch die Abfrage mit `PTS + 1 µs` erhalten und wird nochmals als Keyframe bestätigt.

Kann kein gültiger vorheriger Keyframe ermittelt werden, bricht das Projekt mit einer klaren Fehlermeldung ab. Es gibt keinen Fallback auf das ursprüngliche, möglicherweise zwischen Keyframes liegende PTS.

Nur der Beginn eines neu einsetzenden Keep-Segments wird zum vorherigen Keyframe verschoben. Das Ende des vorausgehenden Filmsegments bleibt an der gewünschten exklusiven Comskip-Grenze: Dort endet ein bestehender Decoderlauf; der nach der entfernten Werbung neu beginnende Decoderlauf ist durch seinen separat geprüften Keyframe abgesichert.

Beginnt ein automatisch erkanntes Commercial mit Comskip-Frame 1, entsteht kein einzelnes Keep-Frame davor. Endet es beim letzten gültigen Comskip-Frame, entsteht kein leeres Schlusssegment. Der danach beginnende Filmabschnitt wird in jedem Fall keyframe-sicher gestartet; erkannter Vor- oder Nachlauf kann zugunsten eines sicheren Copy-Schnitts teilweise wieder enthalten sein.

## Verifikation der Sicherheitslogik

Die abschließende Prüfung des aktuellen lokalen Workflows ergab:

- Syntaxprüfung erfolgreich,
- 14 von 14 gezielten Grenzfalltests bestanden,
- zwei reale Avidemux-2.8.1-CLI-Projekte erfolgreich aufgebaut,
- reale Keyframe-Wiedereinstiege einschließlich PTS-Offset validiert,
- `getPrevKFramePts(...)` bewusst vor `clearSegments()` ausgeführt,
- Referenz-PTS über `getTimeOffsetForSegment(0)` korrekt zwischen linearer Timeline und `addSegment(...)` umgerechnet,
- tatsächliches Referenzende für EOF-Keep-Segmente verwendet,
- Original-MP4s nicht verändert und kein finales Testvideo gespeichert.

---

# 33. Avidemux Cut Points

Die Übergänge zwischen den zusammengesetzten Segmenten erscheinen in Avidemux als Cut Points / Segmentgrenzen.

Navigation:

- Umschalt + Pfeil runter → vorheriger Cut Point
- Umschalt + Pfeil hoch → nächster Cut Point

Diese Punkte dienen zur schnellen Kontrolle der automatisch entfernten Werbung.

Nicht mit Marker A/B verwechseln.

---

# 34. Finaler Avidemux-Crop

Jeder Film benötigt am Ende mindestens eine Prüfung bzw. einen Crop von Anfang und Ende.

Im Copy-Modus:

- Filmanfang → möglichst vorherigen Keyframe wählen
- Marker A setzen
- Filmende → möglichst nächsten Keyframe wählen
- Marker B setzen
- Marker B ist ausschließend
- mit Strg+S den Bereich A–B speichern

Lieber einige Sekunden Vor-/Nachlauf behalten als zwischen Keyframes schneiden und sichtbare Artefakte riskieren.

---

# 35. Bekannter einzelner Avidemux-Sonderfall

Ein konkretes MP4 (`Pompo-The-Cinephile...`) ließ sich mit VLC und Comskip öffnen, aber Avidemux stürzte beim direkten Laden im MP4-Demuxer ab.

Dieser Fehler betrifft nicht die MANUELL-Start-BAT, da dieselbe Datei auch beim normalen direkten Öffnen in Avidemux fehlschlägt und andere MANUELL-Filme mit derselben BAT-Logik funktionieren.

Der Benutzer möchte daraus derzeit **kein Entwicklungsprojekt** machen.

Nicht ungefragt mit Codex untersuchen oder eine Reparaturautomatik bauen.

---

# 36. Finale Logo-Architektur

Der zuvor problematische Logo-Fall ist mit einer praktisch freigegebenen, vollständig projektinternen Lösung abgeschlossen.

## Lern-Sperrzonen

- Die ersten 6 Minuten werden nicht zum Logo-Lernen verwendet.
- Die letzten 6 Minuten werden nicht zum Logo-Lernen verwendet.
- Nach dem Lernen wird trotzdem die komplette Aufnahme von Anfang bis Ende analysiert.

## Multiwindow-Comskip-Sensor

- Im gültigen Mittelbereich werden fünf getrennte, nicht überlappende Lernfenster verwendet.
- Kandidatenmasken bleiben getrennt; es wird keine künstliche Mischmaske erzeugt.
- Gewählt wird eine über mehrere Fenster wiederkehrende Maske statt eines blinden einzelnen Frühkandidaten.
- Comskips schnelles lokales Kantenmatching mit Edge-Maske und `currentGoodEdge` bleibt erhalten.
- Eine schlechte globale `logoPercentage` gilt nur noch als Reliability und vernichtet keine vorhandene lokale Logo-Evidenz.

## Interner zweiter Logosensor und Fusion

- Der zweite unabhängige Sensor liegt vollständig im Comskip-Projekt und in `comskip-final.exe`.
- Er lernt im gültigen Mittelbereich eine stabile Heatmap-Region und Medianreferenz und prüft die komplette Aufnahme korrelationsbasiert.
- Jedes Frame wird weiterhin bewertet; es gibt kein Sampling.
- `overlay_present_score_from_crop()` läuft mit 8 Workern parallel. Score-Mathematik, Gray, Blur, Canny, Korrelation, Schwellenwerte und zeitliche Stabilisierung sind unverändert.
- Maximal 16 Frames/Futures befinden sich gleichzeitig in flight.
- Der Vergleich über 10.000 identische Ray-Frames ergab 0 Abweichungen bei Framenummer, Gray-/Edge-Score, gerundeten Scores, Rohzuständen und stabilisierten Zuständen.
- Zeitliche Stabilisierung und PTS-Zuordnung bleiben Bestandteil der getesteten Implementierung.
- Die Fusion hält `PRESENT`, `ABSENT`, `CONFLICT` und `UNKNOWN` getrennt.
- Findet der interne Sensor keinen belastbaren Kandidaten, bricht die Gesamtanalyse nicht mehr ab. Der Sensor wird für diesen Film als `UNAVAILABLE`/`UNKNOWN` behandelt und liefert neutrale Evidenz; Comskips lokale Logo-Evidenz und die übrige Pipeline laufen weiter. Dieser Fall wurde real mit Puls verifiziert.
- Es gibt keine Runtime-Abhängigkeit vom externen separaten Sensor AdFinder, dessen Datenbank oder Programmdateien.
- Das externe AdFinder-Projekt blieb unverändert.

## Comskip-Framearray-Reuse und Performance

- Der erste Comskip-Vollscan arbeitet weiterhin auf dem Video und persistiert zusätzlich das vollständige Framearray über `--csvout` / `OutputFrameArray()`.
- Die Fusion verändert ausschließlich die Logo-Evidenz.
- Der finale Comskip-Lauf liest die Framearray-CSV über den vorhandenen `loadingCSV` / `ProcessCSV()`-Pfad ein und führt Re-Score, Blockbildung und Ausgabe durch. Das MP4 wird dabei nicht erneut dekodiert.
- `comskip.c` musste dafür nicht verändert werden.
- Ray & Liz (348.500 Frames, 50 fps, 1280x720): neue Gesamtlaufzeit einschließlich Publish/Cleanup `431,9720 s` (ca. 7:12 min), alte Baseline `830,8442 s` (ca. 13:51 min).
- Verbesserung: `399,0421 s` bzw. `48,0285 %`.
- CSV-Re-Score: `17,8342 s`; alter zweiter Video-Vollscan: `264,5115 s`.

## Exakte Framearray-Semantik und Validierung

Für den regulären direkten Comskip-Lauf mit `--csvout` gilt mit `P = Frames Processed`: `OutputFrameArray()` schreibt exakt die zusammenhängenden CSV-Indizes `1 ... P-1`. Damit müssen sowohl die Datenzeilenzahl als auch der letzte CSV-Index exakt `P-1` sein. `ProcessCSV()` rekonstruiert aus N zusammenhängenden Einträgen `1 ... N` intern wieder `frame_count = N+1` und verwendet weiterhin den vorhandenen CSV-Re-Score-Pfad für Blockbildung, Gewichtung und Ausgabe.

Der Validator liest `Frames Processed` aus `sensor\sensor.log`; bei angehängten Wiederaufnahmen ist der letzte passende Eintrag maßgeblich. Er verlangt Startindex 1, lückenlose streng fortlaufende Indizes, den letzten Index `P-1` und exakt `P-1` Datenzeilen. Dafür wird keine `+/-`-Toleranz verwendet. Die bestehende FFprobe-Plausibilitätsprüfung bleibt davon unabhängig und unverändert.

`FILE PROCESSING COMPLETE <N> FRAMES` ist kein verarbeiteter Framezähler, sondern wird PTS-basiert aus dem letzten exportierbaren Framearray-Eintrag zurückgerechnet. Dieser Wert bleibt Diagnoseinformation und wird nicht mehr mit der CSV-Zeilenanzahl gleichgesetzt.

Die Regel wurde praktisch bestätigt:

- Pompo: `177432 Frames Processed`, 177431 CSV-Zeilen; vollständig akzeptiert, Gesamtprozess erfolgreich, visuelle Erkennung sehr gut.
- Outsider: `396745 Frames Processed`, 396744 CSV-Zeilen, `FILE PROCESSING COMPLETE 396743`; vollständig akzeptiert, Gesamtprozess erfolgreich, visuelle Erkennung sehr gut.

Die vorhandene CSV-Re-Score-Architektur und sämtliche Erkennungs-, Sensor-, Fusions- und Scoringregeln blieben unverändert.

Die FINAL_STAGE-Intervalle blieben exakt:

- Ray & Liz: `1-20783`, `332136-348496`
- Puls: `35122-47497`, `79138-88558`, `122108-132964`, `164325-174473`, `201467-201496`

## Temporäre Arbeitsdaten

Interne Laufverzeichnisse verwenden jetzt kurze, vom Filmnamen unabhängige Pfade unter `%TEMP%\ComskipFinal\r\<10-stellige-ID>\run\...`, beispielsweise `%TEMP%\ComskipFinal\r\<ID>\run\learn\w1\w1.logo-raw.csv`, und werden nach erfolgreicher Analyse vollständig entfernt. Ein zuvor real problematischer `*.logo-raw.csv`-Pfad hatte 261 Zeichen; derselbe Pfadtyp hatte mit der neuen Struktur 91 Zeichen, der längste getestete interne Pfad 104 Zeichen. Öffentliche Output-Dateinamen und der vollständige Filmname in Logs und Metadaten bleiben unverändert.

Die große Framearray-CSV ist nur temporär, wird zusammen mit dem Run-Workspace entfernt und nicht in Diagnostic-ZIPs aufgenommen. Diagnosepakete und Traces verwenden ebenfalls die kurze Run-ID statt des langen Filmnamens. Bei Fehlern kann ein kompaktes Diagnosepaket unter `%TEMP%\ComskipFinal\diagnostics` entstehen. Im normalen Downloads-Ordner bleiben keine Arbeitsordner nach dem Muster `.<Filmname>-comskip-*` zurück. Der Pfadfix änderte keinerlei Erkennungslogik.

Nach der Logoebene arbeiten weiterhin die normalen Comskip-Detektoren und Blockheuristiken, insbesondere Blackframe, Aspect Ratio, Resolution und die vorhandene Commercial-Auswertung. Das finale Ergebnis ist ausdrücklich `FINAL_STAGE`, nicht eine reine Logo-Ausgabe.

## Praktische Freigabe

Die FINAL_STAGE-Ergebnisse der fünf Referenzfilme wurden vom Benutzer visuell als fehlerfrei freigegeben. Bei der Finalisierung wurde American Assassin als repräsentativer Golden-Test mit dem finalen entkoppelten Code erneut ausgeführt. Die komplette FINAL_STAGE-Datei war exakt identisch; die Commercial-Intervalle waren:

- `37776-51274`
- `86920-95496`
- `126819-136310`
- `167148-177337`
- `199199-214746`

Der finalisierte Stand bestand 48/48 Python-Tests sowie 6/6 gezielte Framearray-Validator-Tests; Syntaxprüfung und `git diff --check` bestanden ebenfalls. Der erfolgreiche reale Ray-Lauf endete mit Returncode 0, vollständigem Cleanup und 0 verwaisten Prozessen. Bei der Dokumentationsfinalisierung wurden bewusst kein neuer Build, keine erneute Testausführung und kein weiterer Film- oder Benchmarktest durchgeführt.

---

# 37. Strikte Trennung: Python-Workflow versus C-/Git-Projekt

## Python-Workflow

`dist\ComSkip\_Workflow\Werbung entfernen.py`

- lokal,
- nicht Git-getrackt,
- keine Feature-Branches,
- keine Commits nötig,
- nicht pushen oder mit dem Comskip-Projekt synchronisieren,
- direkt lokal testen,
- `dist\ComSkip` separat sichern.

Der lokale `Werbung entfernen.py`-Workflow blieb bei der Performance-/CSV-Reuse-Finalisierung unverändert. `D:\SysOp` ist kein Entwicklungs-, Build-, Deploy- oder Synchronisationsziel.

## Comskip/ComskipGUI

Repository:

`D:\PythonProjekte\ComSkip Fork`

- Git-getrackt,
- Feature-Branch,
- Build,
- Portable-Testdeploy,
- praktischer Test,
- Fast-Forward nach `custom`,
- Push,
- stabiler Tag.

Diese beiden Bereiche niemals in einem Codex-Auftrag vermischen, außer eine Aufgabe erfordert ausdrücklich eine koordinierte Änderung.

---

# 38. Entwicklungsregeln für zukünftige Änderungen

1. Erst tatsächlichen Zustand prüfen.
2. Read-only-Analyse bevorzugen.
3. Kleine, begrenzte Änderungen.
4. Probleme getrennt behandeln.
5. Keine unnötigen Refactorings.
6. `custom` vor praktischem Test nicht bewegen.
7. Performance nicht opfern.
8. Keine Timer-/Debounce-/Throttle-Lösungen für Navigation.
9. Keine zusätzlichen Paint-Runden ohne zwingenden Grund.
10. Für GUI-Test nur nötige Datei deployen.
11. DLLs/config/workflow nicht unnötig ersetzen.
12. Praktischer Test des Benutzers ist Freigabegate.
13. Nach Erfolg kontrolliert integrieren; Fast-Forward bevorzugen, wenn sinnvoll, sonst einen klaren Merge-Commit verwenden.
14. GitHub und Tags sauber synchronisieren.
15. Portable getesteten Stand bei der Integration nicht unnötig erneut überschreiben.
16. Wenn eine Annahme direkt prüfbar ist, prüfen statt raten.
17. Keine PR-Infrastruktur ohne Nutzen.
18. Vom Benutzer ausdrücklich geschlossene Themen nicht ungefragt wieder öffnen.

---

# 39. Praktische Testphilosophie

Automatisierte Tests und Builds sind notwendig, ersetzen aber nicht den praktischen Test.

Typischer Ablauf:

- Codex analysiert.
- Codex implementiert minimal.
- Build/Test erfolgreich.
- Testdatei nach Portable deployen.
- Benutzer arbeitet real mit der Funktion.
- Erst wenn der Benutzer „funktioniert“ bestätigt, wird ein Git-Feature stabil integriert.

Beim lokalen Python-Workflow gilt analog:

- isolierte Tests,
- keine realen Entscheidungsdateien für Tests verändern,
- danach praktischer Workflow-Test.

---

# 40. Aktueller praktisch freigegebener Python-Workflow

Zum Stand dieser Übergabe wurden praktisch erfolgreich getestet:

- E-Menü zeigt gezielt Filme und erlaubt erneute Prüfung.
- CROP-Film erneut öffnen und per Enter CROP-Artefakte neu erzeugen.
- MANUELL-Film erneut öffnen und per Enter MANUELL-Artefakte einschließlich neuer MANUELL-Start-BAT erzeugen.
- MANUELL-Start-BAT öffnet bei normalen Dateien die Original-MP4 ohne automatische Schnitte.
- CROP + gespeicherte TXT-Änderung + Q regeneriert passende CROP-Artefakte.
- CROP/MANUELL + unveränderte TXT + Q erzeugt nichts neu.
- OFFEN + gespeicherte TXT-Änderung + Q bleibt OFFEN und erzeugt keine Entscheidung.
- C oder M erzeugt anschließend erwartungsgemäß die gewählte Entscheidung.

Der Workflow verwendet für neue Analysen `comskip-final.exe` und fällt nur dann auf `comskip.exe` zurück, wenn der finale Launcher nicht vorhanden ist.

Aktueller SHA-256 von `Werbung entfernen.py`:

`652B1FE9E96E9792D92E7B536B780260354C86F06ECC9E1BBA9CCE21CE8CCF8E`

---

# 41. Aktueller praktisch freigegebener GUI-Stand

Branch/Commit:

`custom` → technischer Stand `0016b5c1ab989648ca75eac02c54ffd3b6dd1dd0`

Tag:

`custom-2026-08-18-4` (`custom-2026-08-18-3` bleibt unverändert als vorheriger stabiler Stand)

Portable GUI:

`dist\ComSkip\ComskipGUI.exe`

SHA-256:

`53AADCF4BB86EFB83593128B70AC5CA4176E2DB0CF59D25A6B0579FA6E5061A8`

Dieser Stand enthält:

- Layout-/Resize-Fixes,
- Videozentrierung,
- Scrubbing-Capture-Verhalten,
- Double Buffering,
- Graph-Cleanup,
- saubere Marker,
- zuverlässige Sichtbarkeit kurzer Commercial-Blöcke,
- saubere Timeline-Ränder und konsistentes Mapping,
- korrigierte vertikale Tastaturrichtung: Down `+1 s`, Up `-1 s`, Page Down `+20 s`, Page Up `-20 s`.

---

# 42. Backup-Strategie

GitHub sichert den Git-/C-/GUI-Quellstand.

Die Portable-Umgebung muss separat gesichert werden.

Nach einem praktisch freigegebenen Stand ist ein Backup des gesamten Ordners sinnvoll:

`D:\PythonProjekte\ComSkip Fork\dist\ComSkip`

Damit werden insbesondere auch gesichert:

- aktuelle `ComskipGUI.exe`,
- `comskip.exe`,
- DLLs/config,
- `_Workflow`,
- aktuelle `Werbung entfernen.py`,
- `ComSkip Manual.html`,
- `ComSkip_KI_Projektuebergabe.html`,
- diese KI-Projektübergabe.

---

# 43. Diese Übergabe aktuell halten

Diese Datei nach größeren stabilen Änderungen aktualisieren, insbesondere wenn sich ändern:

- `custom`-Commit,
- stabiler Tag,
- Portable-GUI-SHA,
- Python-Workflow-SHA,
- Hauptmenü,
- C/M/Q/E-Semantik,
- Avidemux-Generatorlogik,
- Deploy-Konvention,
- Verzeichnisstruktur,
- wichtige bekannte Fixes,
- bewusst geschlossene Themen.

Die Datei soll ein aktuelles Gesamtbild liefern und kein vollständiges Commit-Changelog ersetzen.

Nach einem stabil abgeschlossenen Projekt kann Codex sinngemäß angewiesen werden:

> Aktualisiere `ComSkip_KI_Projektuebergabe.md` auf den gerade stabil übernommenen Stand. Ändere nur tatsächlich veraltete Angaben und ergänze neue dauerhaft relevante Projektkenntnisse.

---

# 44. Quellen und Zustände, auf denen diese Übergabe basiert

Die Projektübergabe basiert auf den im Projektverlauf verifizierten bzw. praktisch getesteten Informationen aus:

- Git-Status, Branches, Commits und Tags,
- `comskip.c`,
- `video_out_dx.c`,
- aktueller Portable-GUI,
- `Werbung entfernen.py`,
- `Werbung entfernen Start.bat`,
- Comskip-TXT/LOG/EDL-Testfällen,
- Avidemux-Projektdateien,
- praktischen Benutzer-Tests,
- `ComSkip Manual.html` und `ComSkip_KI_Projektuebergabe.html`.

Bei einem neuen Entwicklungsauftrag sind aktuelle Zustände trotzdem erneut zu verifizieren, wenn sie sich seit dem oben genannten Stand geändert haben könnten.
