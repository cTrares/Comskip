# LogoFinder – technische Übergabe für WeDoMovies

Stand der Analyse: 22.08.2026
Analysierte LogoFinder-Baseline: Git-Commit `5a6b389`
Zweck dieses Dokuments: LogoFinder technisch erklären, ohne dem Zielprojekt direkten Zugriff auf das LogoFinder-Repository zu geben.

## 1. Kurzfassung

LogoFinder ist eine lokale Windows-/Python-Anwendung zur Erkennung von Sender- oder Programm-Overlays in Videodateien und zur Ableitung möglicher Werbeunterbrechungen aus dem zeitweisen Verschwinden dieses Overlays.

Die zentrale Hypothese lautet:

> Während des eigentlichen Films ist ein Senderlogo oder Programm-Overlay über längere Zeit stabil sichtbar. In Werbung verschwindet es oder ändert sich deutlich. Eine zusammenhängende Phase mit niedrigem Overlay-Score ist deshalb ein Werbeverdacht, aber kein endgültiger Beweis.

LogoFinder implementiert drei technisch unterschiedliche Fähigkeiten:

1. **Manuell geführter, vorlagenbasierter Werbescan:** Ein Mensch markiert das sichtbare Logo in einem Screenshot dieses Films. LogoFinder kalibriert diese Vorlage und scannt anschließend denselben Film nach längeren Phasen ohne Treffer.
2. **Vollautomatische Overlay- und Werbeerkennung:** LogoFinder sucht ohne bekannte Vorlage ein zeitlich stabiles Overlay in den vier Bildecken, baut daraus eine robuste Referenz und sucht in der Timeline nach dessen Verschwinden.
3. **Trainierte Logo-Bibliothek und automatische Logo-Zuordnung:** Manuell markierte Logo-Varianten werden gruppiert und als Modelle gespeichert. Diese Modelle können bekannte Logos in weiteren Filmen erkennen. Diese Funktion klassifiziert bzw. ordnet Logos zu; sie ist allein noch keine Werbeblockerkennung.

Für WeDoMovies ist Fähigkeit 2 am einfachsten als zusätzlicher unabhängiger Detektor nutzbar. Fähigkeit 1 ist besonders wertvoll als benutzergeführter Fallback. Fähigkeit 3 ist interessant, wenn das Zielprojekt eine langfristig lernende Logo-Bibliothek aufbauen soll.

## 2. Wichtige Begriffe

- **Logo / Senderlogo:** Das vom Sender eingeblendete grafische Zeichen.
- **Programm-Overlay:** Der allgemeinere Begriff. Der automatische Detektor weiß semantisch nicht, ob der stabile Bildbereich wirklich ein Logo ist. Er erkennt zunächst nur eine wiederkehrende, ortsfeste Struktur.
- **ROI / Rechteck:** Der begrenzte Bildbereich, in dem sich das Overlay befindet.
- **Template / Vorlage:** Ein ausgeschnittener Logo-Bildbereich.
- **Logo-Variante:** Eine einzelne gespeicherte Vorlage aus einem bestimmten Film und einer bestimmten Auflösung.
- **Logo-Modell:** Eine Gruppe ähnlicher Varianten desselben Logos.
- **Present Score:** Ähnlichkeitswert zwischen der Overlay-Referenz und dem Bildbereich an einem Timeline-Punkt.
- **Werbekandidat:** Ein Zeitintervall, in dem das Overlay ausreichend lange als nicht vorhanden bewertet wird.

## 3. Systemübersicht

```text
Videodatei
   |
   +-- A: Mensch markiert ROI -----------------------------+
   |                                                       |
   |   Screenshot -> Crop -> Kalibrierung -> 20-s-Scan     |
   |                                      -> Logo fehlt     |
   |                                      -> Werbeverdacht  |
   |                                                       |
   +-- B: automatische Overlay-Suche ----------------------+--> Ergebnis / Werbekandidaten
   |                                                       |
   |   Eckzonen -> Heatmap -> beste ROI -> Medianreferenz   |
   |                         -> 60-s-Grobscan               |
   |                         -> 5-s-Feinscan                |
   |                         -> Logo fehlt                  |
   |                         -> Werbeverdacht               |
   |                                                       |
   +-- C: manuelles Logo-Training -> Varianten/Modelle -----+
                               |
                               +-> bekannte Logos in anderen Filmen zuordnen
```

Die Pfade A und B beantworten dieselbe fachliche Frage auf unterschiedliche Weise: „Wann ist das erwartete Programm-Overlay nicht mehr da?“ Pfad C beantwortet zuerst eine andere Frage: „Welches bekannte Logo ist in diesem Film vorhanden?“

## 4. Workflow A: manuell geführter, vorlagenbasierter Werbescan

### 4.1 Bedienablauf

1. Der Benutzer startet den normalen Workflow.
2. LogoFinder wählt den nächsten offenen Film.
3. Bei zunächst 60 Sekunden wird ein Screenshot erzeugt.
4. Der Benutzer zieht mit der Maus ein Rechteck um das kleine, dauerhaft eingeblendete Senderlogo.
5. Ist das Logo dort nicht brauchbar sichtbar, kann der Benutzer den nächsten Screenshot anfordern. Der Zeitpunkt wird jeweils um weitere 60 Sekunden verschoben.
6. Die markierte ROI wird auf die native Videoauflösung zurückgerechnet und als PNG-Vorlage gespeichert.
7. LogoFinder kalibriert die Vorlage an zehn über den Film verteilten Stellen.
8. Ist die Vorlage brauchbar, scannt LogoFinder den Film in 20-Sekunden-Schritten.
9. Sobald das Logo über mindestens zwei aufeinanderfolgende Messpunkte bzw. 40 Sekunden nicht erkannt wird, entsteht ein Werbeverdacht ab dem ersten fehlenden Messpunkt.
10. Der erste Verdacht beendet den Scan. Das aktuelle Verhalten liefert bei diesem manuellen Scan also nicht alle Werbeblöcke, sondern den ersten ausreichend langen Logoausfall.

### 4.2 Koordinatentransformation

Der Screenshot kann in der GUI skaliert dargestellt sein. Die Auswahlkoordinaten werden deshalb von der Screenshotgröße auf die tatsächliche Videogröße übertragen:

```text
x_video = round(x_screenshot * video_width  / screenshot_width)
y_video = round(y_screenshot * video_height / screenshot_height)
```

Die Vorlage wird anschließend exakt auf die Größe dieses nativen Video-Rechtecks skaliert. Um geringe Verschiebungen zu tolerieren, wird die Such-ROI um 18 % der Template-Breite und -Höhe erweitert, mindestens jedoch um sechs Pixel pro Richtung.

### 4.3 Template-Vorbereitung und Matching

Die manuelle Scan-Engine verarbeitet die Vorlage wie folgt:

- Umwandlung in Graustufen.
- Gauß-Glättung mit einem `3x3`-Kernel.
- Canny-Kanten mit Schwellwerten `30/100`.
- Dilatation der Kanten mit `3x3`.
- Falls weniger als 25 Maskenpixel übrig bleiben, wird eine einfache Binärmaske als Fallback erzeugt.
- Matching per `cv2.matchTemplate` mit `TM_CCORR_NORMED` und Maske.
- Liegt der beste Treffer zu weit von der erwarteten Position entfernt, wird der Score mit `0,65` abgewertet.

Der feste Treffer-Schwellwert ist `0,80`.

### 4.4 Kalibrierung

Vor dem vollständigen Scan wird verhindert, dass eine schlechte Markierung sofort viele Fehlalarme erzeugt:

- Filme unter 40 Minuten gelten für diesen Pfad als `Kurzfilm` und werden nicht vollständig gescannt.
- Zehn Kalibrierungspunkte liegen gleichmäßig zwischen 8 % und 92 % der Filmdauer.
- `max_score < 0,80` führt zu `Pruefen`.
- Mindestens fünf gute Messpunkte führen zu `Gut`.
- Ein erreichter Schwellwert, aber weniger als fünf gute Punkte, führt zu `Unsicher`.
- Nur der Status `Gut` gelangt in den vollständigen Scan. `Pruefen`, `Unsicher` und Fehler werden zur manuellen Nachkontrolle zurückgegeben.

### 4.5 Timeline-Scan

```text
CHECK_INTERVAL_SECONDS = 20
NO_LOGO_SECONDS         = 40
MATCH_THRESHOLD         = 0.80
```

Alle Messzeiten werden zuerst aufgebaut und dann parallel in Teilmengen ausgewertet. Die Anzahl paralleler Scan-Worker wird aus der CPU-Anzahl abgeleitet und auf zwei bis acht begrenzt.

Für jeden Messpunkt gilt:

```text
score >= 0.80  -> Logo vorhanden -> laufende Fehlphase zurücksetzen
score <  0.80  -> Logo fehlt     -> Fehlphase beginnen oder fortsetzen
Fehlphase >= 40 Sekunden          -> erster Werbeverdacht
```

### 4.6 Ergebnis

Der Rückgabewert `ScanResult` enthält:

- Status `Verdacht`, `Kein Fund` oder `Fehler`.
- Startzeit des ersten Verdachts.
- Bester beobachteter Template-Score.
- Optional einen Screenshot am Beginn des Verdachts.

### 4.7 Stärken und Grenzen

Stärken:

- Der Mensch legt die korrekte semantische ROI fest.
- Sehr verständliches und überprüfbares Verfahren.
- Gut als Fallback bei schwierigen oder ungewöhnlich positionierten Logos.
- Geringe Gefahr, versehentlich einen beliebigen stabilen Bildbestandteil als Logo zu wählen.

Grenzen:

- Pro Film ist zunächst eine menschliche Markierung nötig.
- Der Scan stoppt beim ersten Werbeverdacht.
- Ein einzelner globaler Schwellwert reagiert empfindlich auf Transparenz, Animation, Skalierung und wechselnden Hintergrund.
- 20-Sekunden-Raster und 40-Sekunden-Regel begrenzen die zeitliche Genauigkeit.
- Die Mindestfilmlänge von 40 Minuten ist eine Produktentscheidung, keine technische Notwendigkeit.

## 5. Workflow B: vollautomatische Overlay- und Werbeerkennung

Dieser Pfad benötigt weder eine manuell markierte Vorlage noch ein zuvor trainiertes Senderlogo.

### 5.1 Phase 1 – Kandidatenbilder über den Film verteilen

Standardmäßig werden für die Overlay-Suche 24 Frames verwendet. Die Messzeiten liegen gleichmäßig in einem robusten inneren Bereich des Films:

- Beginn: das kleinere von fünf Minuten und 8 % der Filmdauer.
- Ende: das kleinere von einer Minute vor Filmende und 92 % der Filmdauer.
- Bei problematisch kurzer Dauer wird auf nahezu den gesamten Film ausgewichen.
- Mindestens zwölf lesbare Frames sind für die Heatmap erforderlich.

Damit sollen Vorspann, Abspann und einzelne Sonderbilder weniger Einfluss haben.

### 5.2 Phase 2 – Suche nur in typischen Eckzonen

Die Suche wird auf vier normalisierte Zonen begrenzt:

```text
oben rechts : x=55..100 %, y= 0..35 %
oben links  : x= 0..45 %,  y= 0..35 %
unten rechts: x=55..100 %, y=65..100 %
unten links : x= 0..45 %,  y=65..100 %
```

Die Eckzonen erhalten unterschiedliche Prioritäten:

```text
oben rechts  1,10
oben links   1,06
unten rechts 0,92
unten links  0,72
```

LogoFinder bevorzugt damit bewusst obere Senderlogo-Positionen. Für WeDoMovies sollte diese Heuristik konfigurierbar gemacht werden.

### 5.3 Phase 3 – Heatmap für ortsfeste Strukturen

Jede Eckzone wird bei Bedarf auf 420 Pixel Breite verkleinert. Pro Sample entstehen:

- ein geglättetes Graubild,
- ein Canny-Kantenbild,
- über alle Frames eine Kantenhäufigkeit,
- ein mittleres Bild mit dessen Kanten,
- die zeitliche Standardabweichung je Pixel.

Die Heatmap kombiniert drei Hinweise:

```text
heat = 0,45 * normalisierte Kantenhäufigkeit
     + 0,35 * Kanten des zeitlichen Mittelbilds
     + 0,20 * inverse zeitliche Bewegung
```

Ein Senderlogo ist typischerweise strukturiert, erscheint wiederholt an derselben Stelle und bewegt sich wenig. Genau diese Eigenschaften erzeugen einen hohen Heat-Wert.

### 5.4 Phase 4 – Komponenten und Kandidatenfilter

Die Heatmap wird mindestens bei `0,28` bzw. am `96,5`-Perzentil binarisiert. Morphologische Operationen schließen kleine Lücken und verbinden benachbarte Pixel. Danach werden zusammenhängende Komponenten bewertet.

Wichtige geometrische Grenzen relativ zum Gesamtbild:

```text
Flächenanteil:  0,018 % bis 1,8 %
Breitenanteil:  1,0 %   bis 19,0 %
Höhenanteil:    1,0 %   bis 17,0 %
max. Seitenverhältnis: 4,5
max. Randberührung:    0,58
```

Lange horizontale Linien und streifenartige Komponenten werden entfernt. Zu große Komponenten werden nochmals in kleinere Unterkomponenten zerlegt. Das ist insbesondere bei großen Bauchbinden, Rahmen oder breiten Textbalken wichtig.

Der Kandidaten-Score kombiniert:

```text
45 % Heat
28 % Kantenhäufigkeit
12 % Kanten im Mittelbild
 8 % Kompaktheit
 7 % bevorzugte Größe
anschließend Multiplikation mit der Zonenpriorität
```

Das Rechteck des Kandidaten wird abschließend um 28 % erweitert, mindestens um sechs Pixel. Maximal vier Kandidaten werden zurückgegeben; der Werbedetektor verwendet aktuell nur den bestbewerteten Kandidaten.

### 5.5 Phase 5 – robuste Overlay-Referenz

Für den besten Kandidaten werden standardmäßig acht weitere, gleichmäßig verteilte ROI-Ausschnitte gelesen:

1. Graustufenwandlung.
2. `3x3`-Glättung.
3. Histogramm-Equalisierung.
4. Pixelweiser Median über alle Ausschnitte.

Der Median unterdrückt wechselnde Filminhalte und bewahrt Strukturen, die im Kandidatenbereich häufig gleich bleiben.

Aus der Medianreferenz werden erzeugt:

- Graureferenz,
- Canny-Kantenreferenz mit `35/110`,
- eine Prominenz-/Kantenmaske,
- eine Kantenmaske für das spätere Matching.

Lange horizontale Linien werden auch hier entfernt. Ist die Maske zu klein, wird auf eine vollständige Maske zurückgefallen.

### 5.6 Phase 6 – Present Score

Für jeden Timeline-Frame wird dieselbe ROI ausgeschnitten und normalisiert. Danach werden zwei maskierte Template-Matches berechnet:

```text
present_score = 0,76 * edge_score + 0,24 * gray_score
```

Der Wert wird auf `0..1` begrenzt. Bei `present_score >= 0,42` gilt das Overlay als vorhanden.

Die Kanten erhalten das stärkere Gewicht, weil sie gegenüber wechselnden Farben und Bildhintergründen robuster sind als rohe Grauwertähnlichkeit.

### 5.7 Phase 7 – zweistufige Timeline

Grobscan:

- Messpunkt alle 60 Sekunden.
- Fehlende Punkte in den ersten fünf Minuten werden nicht zur Bildung von Verfeinerungsfenstern verwendet.
- Ein einzelner grober Fehlpunkt erzeugt nur dann ein Fenster, wenn sein Score höchstens `0,24` ist.
- Eine Gruppe aus mindestens zwei Fehlpunkten darf bis `0,36` reichen.
- Verfeinerungsfenster erhalten 90 Sekunden Vor- und Nachlauf.

Feinscan:

- Innerhalb dieser Fenster wird alle fünf Sekunden gemessen.
- Zusammenhängende fehlende Punkte werden zu Kandidaten gebaut.
- Ein Kandidat muss mindestens 60 Sekunden dauern.
- Kandidaten mit maximal 60 Sekunden Abstand werden zusammengeführt.
- Kurze Kandidaten unter zwei Minuten bleiben nur erhalten, wenn mindestens ein sehr starker Fehlwert von höchstens `0,18` vorliegt.

### 5.8 Rückgabestrukturen

`ProgramOverlay`:

- `rect`: `(left, top, right, bottom)` in nativen Videopixeln.
- `source`: z. B. `heatmap:oben_rechts`.
- `confidence`: Ranking-Score des Heatmap-Kandidaten.
- `sample_count`: Zahl der tatsächlich verwendeten Frames.

`OverlayTimelinePoint`:

- Sekundenwert und formatierte Zeit.
- `present_score`.
- boolesches `is_present`.

`AdBreakCandidate`:

- Start und Ende in Sekunden und als Zeittext.
- Dauer.
- minimaler und durchschnittlicher Present Score.

Der reine Funktionsaufruf lautet:

```python
overlay, timeline, candidates = detect_ad_breaks_for_video(video_path)
```

Diese Funktion ist der beste konzeptionelle Einstiegspunkt für WeDoMovies.

### 5.9 Prozessisolation und Batch-Verarbeitung

Im normalen Python-Betrieb startet LogoFinder für jeden Film `python -m logo_finder.ad_break_worker <videopfad>`. Der Worker schreibt ein JSON-Ergebnis auf stdout. Das Hauptprogramm:

- setzt ein Timeout von 180 Sekunden,
- behandelt Abstürze als Jobfehler,
- kann unterbrochene Jobs später wieder aufnehmen,
- passt die Zahl paralleler Worker anhand der Laufzeiten an,
- begrenzt langsame Speicherprofile auf einen Worker.

In einer eingefrorenen PyInstaller-Version wird die Erkennung dagegen direkt im Prozess ausgeführt.

Für WeDoMovies ist die Prozessgrenze sehr sinnvoll: Fehlerhafte Codecs, OpenCV-Hänger und hoher RAM-Verbrauch bleiben vom Hauptprozess getrennt.

## 6. Fähigkeit C: trainierte Logo-Bibliothek und automatische Logo-Zuordnung

Diese Fähigkeit ergänzt die Werbeerkennung, muss aber fachlich separat betrachtet werden.

### 6.1 Manuelles Logo-Training

Der Trainingsworkflow zeigt nacheinander Screenshots bei 5, 10, 15, 20, 25, 30 und 35 Minuten. Danach folgen zufällige Punkte, wobei bei längeren Filmen die ersten und letzten 60 Sekunden gemieden werden.

Der Benutzer kann:

- eine mindestens `8x8` Pixel große ROI markieren und speichern,
- zum nächsten Screenshot gehen,
- einen Film als „Kein Senderlogo“ markieren,
- die zuletzt gespeicherte Variante mit `Strg+Z` zurücknehmen.

Die Auswahl wird auf die native Videoauflösung skaliert und unter `Arbeitsverzeichnis/LogoVorlagen` als PNG gespeichert.

### 6.2 Varianten, Gruppen und Ähnlichkeit

Jede Vorlage wird als `logo_variants`-Datensatz gespeichert. Neben Pfad und Quellfilm enthält sie:

- Videoauflösung,
- Templategröße,
- native ROI-Koordinaten,
- Average Hash,
- Qualitätsscore,
- Aktivstatus,
- optionale Duplikatreferenz,
- Cluster-Score,
- Logo-Gruppen-ID.

Neue Varianten werden nur mit aktiven Varianten derselben exakten Videoauflösung verglichen. Der kombinierte Paar-Score besteht aus:

```text
 9 % Average-Hash-Ähnlichkeit
16 % Graubildähnlichkeit
32 % Kantenähnlichkeit
43 % Signatur für neutrale/weiße/graue Logos
```

Ab `0,72` wird die neue Variante als ähnlich betrachtet, derselben Gruppe zugeordnet und zunächst als Duplikat inaktiv gespeichert. Ab `0,48` können zusätzlich Feedback-Kandidaten für eine spätere Bestätigung entstehen.

### 6.3 Modellaufbau

Ein `LogoModel` enthält bis zu sechs Varianten einer Gruppe und derselben Auflösung. Jede Variante besitzt:

- histogrammnormalisiertes Graubild,
- Canny-Kanten,
- Vordergrundmaske,
- Angaben zu Farbsättigung und neutralem Erscheinungsbild.

Für überwiegend neutrale Logos wird eine zusätzliche HSV-basierte Formmaske aufgebaut. Das ist für weiße oder graue Senderlogos vor wechselnden Hintergründen besonders relevant.

Die Modellreife setzt sich zusammen aus:

```text
45 % Variantenanzahl
40 % Kantenstabilität
15 % Hintergrunddiversität
```

Ein Modell gilt als reif, wenn:

- mindestens zwei Rohvarianten existieren,
- die Kantenstabilität mindestens `0,18` beträgt,
- der Reife-Score mindestens `0,45` beträgt.

### 6.4 Automatische Zuordnung bekannter Logos

Die automatische Logo-Suche:

- lädt nur Modelle derselben exakten Videoauflösung,
- prüft ab Minute fünf in Fünf-Minuten-Schritten,
- prüft höchstens 24 Frames und höchstens bis Minute 125 bzw. eine Minute vor Ende,
- verwirft zunächst sehr unruhige Hintergründe,
- führt bei Bedarf einen zweiten Versuch an den festen Zeiten 5 bis 35 Minuten ohne Hintergrundfilter aus.

Das Modellmatching kombiniert Kanten- und Grauwertscore:

```text
neutrales Logo: 82 % Kanten + 18 % Grau
farbiges Logo:  70 % Kanten + 30 % Grau
```

Schwellwerte:

- Einzelne bzw. unreife Modelle: standardmäßig `0,82`.
- Reife Modelle mit mindestens zwei Varianten: `0,78`.

Ein Fund wird mit Logo-Varianten-ID, Score und Zeitpunkt in `logo_matches`, `logo_detection_attempts` und im Film-Datensatz gespeichert.

Wichtig: Dieser Fund sagt „bekanntes Logo vorhanden“. Um daraus Werbeblöcke zu finden, muss das erkannte Modell anschließend kontinuierlich oder zweistufig über die Timeline verfolgt werden. Diese direkte Verbindung ist im derzeitigen Code nicht als eigenständige Pipeline fertig abstrahiert.

## 7. Bedeutung der vier WeDoMovies-Bilder

Die Bilder im Übergabeordner sind gute Beispiele für die Grenzen der Methode:

### `1.png`

Das kleine graue `wedotv Movies`-Overlay oben rechts ist ein guter manueller Trainings- bzw. Scan-Kandidat. Das rote Rechteck sollte eng um das kleine Overlay liegen und den schwarzen Balken nicht unnötig groß einschließen.

### `2.png` und `4.png`

Das große, bildfüllende WeDoMovies-Ident ist **keine** geeignete Vorlage für das dauerhaft eingeblendete Programmlogo. Größe und Position unterscheiden sich stark vom kleinen Overlay in `1.png`. Solche Frames sollten aus dem Training ausgeschlossen oder als eigener Szenentyp klassifiziert werden.

### `3.png`

Das Bild zeigt eine Eigenwerbung bzw. Promo, in der WeDoMovies-Branding weiterhin sehr deutlich vorkommt. Das ist ein wichtiger Gegenfall zur Grundhypothese „Werbung = Logo fehlt“:

- Ein Sender kann sein Branding während Eigenwerbung weiter anzeigen.
- Ein großer roter Rahmen und weitere feste Grafiken können die Heatmap dominieren.
- Ein reiner Logo-Ausfall-Detektor kann diese Werbung übersehen.

Für WeDoMovies sollte Logo-Abwesenheit deshalb nur eine Evidenzspur neben anderen Signalen sein, etwa Schwarzbildern, harten Schnitten, Audio-/Lautheitswechseln, Untertitel-/OCR-Mustern, Dauerregeln oder einem bereits vorhandenen Werbedetektor.

## 8. Relevante Datenbanktabellen

Für eine Übernahme der Erkennungslogik ist die konkrete SQLite-Datenbank nicht erforderlich. Das bestehende Schema zeigt aber, welche Domänenobjekte LogoFinder verwendet:

- `movies`: Videoinventar, Metadaten, Status und letzter Fund.
- `logo_groups`: logische Gruppen ähnlicher Logos.
- `logo_variants`: markierte Einzelvorlagen mit ROI, Auflösung und Qualität.
- `logo_feedback_candidates`: noch zu bestätigende Ähnlichkeitsbeziehungen.
- `logo_matches`: gefundene bekannte Logos in Filmen.
- `logo_detection_attempts`: erfolgreiche und erfolglose Suchläufe.
- `scan_jobs`: persistente, wiederaufnehmbare Jobs.
- `scan_results`: allgemeine Scanergebnisse.
- `ad_break_candidates`: automatisch erkannte Werbeintervalle und Overlay-Metadaten.

Hinweis zum Ist-Zustand: `detect_ad_breaks_for_video` kann mehrere Kandidaten zurückgeben. `replace_ad_break_candidates` speichert derzeit jedoch nur den frühesten Kandidaten. Das Zielprojekt sollte alle Intervalle persistieren oder ausdrücklich dokumentieren, wenn nur der erste Fund benötigt wird.

## 9. Empfohlene Integration in WeDoMovies

### 9.1 Nicht die GUI übernehmen

`logo_marker_scanner.py` enthält rund um Tkinter, CSV, VLC, Batch-Jobs und Statusverwaltung sehr viel anwendungsspezifische Logik. Für das Zielprojekt sollte daraus kein zweiter monolithischer GUI-Pfad kopiert werden.

Empfehlung: eine kleine, zustandsarme Erkennungsbibliothek mit klarer API extrahieren.

```python
@dataclass(frozen=True)
class OverlayDetectionConfig:
    coarse_step_seconds: int = 60
    fine_step_seconds: int = 5
    present_threshold: float = 0.42
    min_break_seconds: int = 60

@dataclass(frozen=True)
class DetectionReport:
    video_path: Path
    overlay_rect: tuple[int, int, int, int] | None
    overlay_confidence: float | None
    timeline: tuple[TimelinePoint, ...]
    candidates: tuple[AdCandidate, ...]
    diagnostics: dict[str, object]

def detect_ads_by_overlay(
    video_path: Path,
    *,
    config: OverlayDetectionConfig,
    manual_rect: tuple[int, int, int, int] | None = None,
    manual_template: np.ndarray | None = None,
) -> DetectionReport:
    ...
```

Eine einzige Schnittstelle kann zwei Modi bedienen:

- ohne `manual_rect`/`manual_template`: automatische Heatmap-Suche,
- mit manueller ROI/Vorlage: benutzergeführter Fallback.

### 9.2 Evidenz statt endgültiger Wahrheit

Der LogoFinder-Detektor sollte im Zielprojekt ein Signal mit Konfidenz liefern, zum Beispiel:

```text
overlay_absence_score
overlay_candidate_start/end
overlay_reference_confidence
overlay_position
minimum/average present score
```

Die endgültige Werbeentscheidung sollte durch die vorhandene WeDoMovies-Logik oder einen Fusionsschritt erfolgen. Beispiel:

```text
hohe Sicherheit:
    Overlay fehlt
    UND vorhandener WeDoMovies-Detektor meldet Schnitt-/Werbemuster

mittlere Sicherheit:
    Overlay fehlt sehr stark und mindestens 60 Sekunden

niedrige Sicherheit / Review:
    nur ein Detektor schlägt an
    ODER Eigenwerbungsbranding bleibt sichtbar
```

### 9.3 Diagnostik unbedingt behalten

Für spätere Kalibrierung sollten pro Film mindestens gespeichert werden:

- erkannte Overlay-ROI,
- Referenzbild und Maske,
- verwendete Sample-Zeiten,
- Heatmap-Kandidaten mit Scores,
- vollständige Present-Score-Timeline,
- grobe und verfeinerte Fenster,
- final akzeptierte und verworfene Kandidaten,
- verwendete Konfiguration und Codeversion.

Damit kann das Zielprojekt Fehlalarme nachvollziehen und Schwellwerte datenbasiert optimieren.

### 9.4 Konfiguration statt fest codierter Werte

Folgende Werte sollten im Zielprojekt konfigurierbar werden:

- Eckzonen und Zonenprioritäten.
- Anzahl und Lage der Referenzsamples.
- Heatmap-Gewichte und Größenfilter.
- Present-Score-Gewichte und Schwelle.
- Grob- und Feinraster.
- Mindestdauer und Zusammenführungsabstand.
- Ignorierter Start-/Endbereich.
- Mindestfilmlänge.

## 10. Welche Dateien sind relevant?

### 10.1 Nur zum Verstehen und Planen

Diese Dateien reichen, wenn das andere Projekt zunächst nur Architektur und Ideen bewerten soll:

- `WeDoMovies Modul/LOGOFINDER_TECHNISCHE_UEBERGABE.md`
- `WeDoMovies Modul/CODEX_BRIEFING_FUER_ZIELPROJEKT.md`
- optional `WeDoMovies Modul/1.png` bis `4.png`

### 10.2 Vollautomatische Overlay-Werbeblockerkennung als Referenzcode

Direkt fachlich relevant:

- `logo_finder/ad_break_detector.py`
- `logo_finder/logo_heatmap_detector.py`
- `logo_finder/logo_position_profile.py`
- `logo_finder/logo_presence_detector.py`
- `logo_finder/ad_break_worker.py`

Technische Importabhängigkeiten des aktuellen Codes:

- `logo_finder/logo_matcher.py`
- `logo_finder/logo_model.py`
- `logo_finder/database.py`
- `logo_finder/paths.py`
- `logo_finder/__init__.py`

Die letzten vier Dateien werden für die reine Heatmap-Idee nur wegen der aktuellen Importkopplung mitgezogen. Im Zielprojekt sollte `read_frame_at`, `seconds_to_display` und die Sample-Zeit-Erzeugung in ein kleines neutrales Video-Hilfsmodul verschoben werden. Dann benötigt die automatische Overlay-Erkennung weder Logo-Bibliothek noch SQLite.

Optional für die aktuelle Persistenz:

- `logo_finder/ad_candidate_store.py`
- `logo_finder/batch_jobs.py`
- `logo_finder/result_store.py`

### 10.3 Manuelles Training und bekannte Logo-Modelle

Kernmodule:

- `logo_finder/logo_library.py`
- `logo_finder/logo_model.py`
- `logo_finder/logo_matcher.py`
- `logo_finder/database.py`
- `logo_finder/paths.py`
- `logo_finder/movie_inventory.py`

Die Benutzeroberfläche, Screenshot-Erzeugung, ROI-Auswahl, Kalibrierung und der manuelle Timeline-Scan befinden sich derzeit in:

- `logo_marker_scanner.py`

Diese Datei sollte nicht vollständig übernommen werden. Relevant sind konzeptionell bzw. für eine gezielte Extraktion:

- `scale_rect`
- `padded_rect`
- `resize_template_to_video`
- `prepare_match_template`
- `match_region`
- `calibrate_template`
- `create_video_snapshot`
- `score_video_timestamps`
- `scan_video`
- `use_training_logo`
- `queue_scan`
- `WorkflowWindow` nur als Referenz für die ROI-Bedienung

### 10.4 Nicht in das andere Projekt kopieren

- `.git/`
- `.venv/`
- `LogoFinder.db`
- `Arbeitsverzeichnis/`
- `Protokolle/`
- `Testvideos/`
- `Sicherungen/`
- `build/`
- `dist/`
- `config.json`
- `filme_status.csv`
- `protokoll.txt`
- `__pycache__/`

Das sind Repository-Metadaten, lokale Laufzeitdaten, personenbezogene Pfade, Tests/Videos oder generierte Artefakte. Das Zielprojekt sollte seine eigene Persistenz und seine eigenen Test-Fixtures verwenden.

## 11. Minimaler Übernahmeplan

1. Dieses Dokument und die vier Beispielbilder in das Zielprojekt kopieren.
2. Dort zunächst nur eine Design-/Review-Aufgabe starten; noch keinen Produktivcode kopieren.
3. Entscheiden, ob nur der vollautomatische Overlay-Detektor oder zusätzlich der manuelle Fallback benötigt wird.
4. Die ausgewählten Kernmodule als **Referenz** kopieren.
5. Video-Hilfsfunktionen von GUI, SQLite und globalen Pfaden entkoppeln.
6. Einen reinen API-Rückgabewert mit allen Kandidaten und Diagnosedaten definieren.
7. Tests mit Fällen wie `1.png` bis `4.png` und echten kurzen Videosegmenten aufbauen.
8. Ergebnisse als zusätzliche Evidenz in den vorhandenen WeDoMovies-Entscheider einspeisen.
9. Erst nach Vergleichsmessungen Schwellwerte verändern oder die Methode produktiv aktivieren.

## 12. Akzeptanztests für das Zielprojekt

Mindestens folgende Fälle sollten geprüft werden:

- Kleines statisches Logo oben rechts auf stark wechselndem Hintergrund.
- Weißes/graues transparentes Logo auf hellem und dunklem Hintergrund.
- Vertikales oder ungewöhnlich schmales Logo.
- Animiertes bzw. pulsierendes Logo.
- Logo wechselt während des Films die Variante.
- Logo verschwindet nur für wenige Sekunden bei Szenenübergängen.
- Echte Werbung ohne Senderlogo.
- Eigenwerbung mit weiter sichtbarem Senderbranding wie in `3.png`.
- Großes Sender-Ident wie in `2.png`/`4.png`.
- Bauchbinden, Untertitel, Uhr, QR-Code und breite rote Rahmen als Störkandidaten.
- Letterbox-Balken und wechselndes Seitenverhältnis.
- Mehrere Werbeblöcke; alle müssen im Ergebnis erhalten bleiben.
- Beschädigte oder sehr langsam seekbare Videodatei; der Worker muss mit Timeout kontrolliert enden.

## 13. Bekannte technische Risiken

- **Grundannahme nicht universell:** Werbung kann das Senderbranding behalten; Filmteile können das Logo verlieren.
- **Nur beste automatische ROI:** Der aktuelle Werbedetektor testet nicht alle vier Heatmap-Kandidaten gegeneinander.
- **Positionsbias:** Obere Ecken werden deutlich bevorzugt.
- **Exakte Auflösungskopplung:** Trainierte Modelle werden nur für identische Breite/Höhe geladen.
- **Statische Grafikfallen:** Uhr, Rahmen, Untertitelbestandteile oder wiederkehrende Promotion-Grafiken können als Overlay erscheinen.
- **Erster Kandidat in Persistenz:** Die aktuelle Datenbankschicht speichert nur den frühesten automatischen Werbekandidaten.
- **Feste Schwellenwerte:** Die Werte wurden heuristisch gewählt und sind nicht auf den WeDoMovies-Datenbestand kalibriert.
- **Zeitauflösung:** Der automatische Grobscan kann sehr kurze Ereignisse zunächst übersehen; der Feinscan läuft nur um verdächtige Grobpunkte.
- **Kein semantisches Verständnis:** OpenCV erkennt Ähnlichkeit und Stabilität, nicht die Bedeutung „Senderlogo“ oder „Werbung“.

## 14. Kernaussage für die Architekturentscheidung

LogoFinder sollte in WeDoMovies nicht als vollständige Anwendung eingebaut werden. Der wertvollste wiederverwendbare Kern ist ein eigenständiger `OverlayAbsenceDetector`:

```text
Video
 -> stabile Overlay-ROI automatisch finden oder manuell vorgeben
 -> robuste Referenz bilden
 -> Present-Score-Timeline erzeugen
 -> Abwesenheitsintervalle vorschlagen
 -> alle Scores und Kandidaten an den vorhandenen WeDoMovies-Entscheider liefern
```

Damit bleibt LogoFinder eine zusätzliche, nachvollziehbare Erkennungsmethode. WeDoMovies behält die Hoheit über Zusammenführung, Priorisierung, Review und endgültige Werbeblockentscheidung.
