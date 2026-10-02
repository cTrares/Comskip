COMSKIP V4.1 FINAL - VERARBEITUNGSPROFILE
=========================================

V4.1 ist der aktuelle portable Stand. Er enthält den kommerziellen
Logo-Makromodus sowie den akzeptierten WeDo-v3-Workflow in comskip-final.exe.

Automatische Auswahl:
- Schnellmodus-Sender.txt   -> öffentlich-rechtlicher V3-Schnellmodus
- wedo-movies im Dateinamen -> autoritativer WeDo-v3-Workflow
- Makromodus-Sender.txt     -> neuer kommerzieller Logo-Makromodus
- alle übrigen Dateien      -> bisherige vollständige Analyse

Der Makromodus wird deutlich im Konsolenfenster, im Log und in einer Datei
<Filmname>.makromodus.txt gekennzeichnet.

Sicherheitslogik und Prüfmarker:
- Kurze Logo-Aussetzer werden zuerst innerhalb eines stabilen Filmblocks
  repariert; erst danach wird über Film- und Werbeblöcke entschieden.
- Stabile positive Filmabschnitte werden nicht still als Werbung überdeckt.
- Orange Null-Längen-Marker werden nur bei einem tatsächlich gemessenen
  stabilen positiven Gegenabschnitt innerhalb eines Werbevorschlags erzeugt.
  Es gibt keine pauschalen Marker in festem Abstand zu Werbeblöcken.
  M/N springt zu vorhandenen Markern. Sie stehen nur in der TXT, niemals als
  Schnitt in der EDL.
- Die Markerübersicht liegt zusätzlich in <Filmname>.pruefmarker.txt.
- Am Blockrand in ComskipGUI die richtige Stelle suchen und B (Beginn) oder
  E (Ende) drücken; J/K sind nur flüchtige Vorher-/Nachher-Marker, L löscht sie.

Senderliste ändern:
Makromodus-Sender.txt mit einem Dateinamen-Token pro Zeile bearbeiten.

Vollständige Analyse für eine einzelne Aufnahme erzwingen:
comskip-final.exe --full-analysis "D:\Pfad\Film_sender_hq.mp4"

Makromodus vorübergehend abschalten:
comskip-final.exe --macro-mode off "D:\Pfad\Film_sender_hq.mp4"

Automatische Eskalation im Batch:
Erzeugt der Makromodus keinen einzigen Schnittblock oder schlägt er technisch
fehl, wird sein Ergebnis verworfen und für diesen Film automatisch die
vollständige Comskip-Analyse gestartet. Der Batch wartet nicht auf eine
Bestätigung. Das bestehende Log und die bestehende Diagnose-JSON nennen den
Grund; es wird keine zusätzliche Ausgabedatei und kein neuer Dateiname erzeugt.
Die angegebene Gesamtlaufzeit enthält beide Stufen.

Sicherheitsprüfung nach Werbeblöcken:
Die erste Rückkehr des Senderlogos beendet einen inneren Werbeblock nicht mehr
sofort. Der Makromodus prüft den folgenden Drei-Minuten-Korridor. Folgt dort
erneut ein belastbarer logo-negativer Werbeabschnitt oder eine lange
logo-positive Insel mit anschließendem Werberückfall, bleibt diese Zwischenphase
Teil des Werbeblocks. Erst die danach stabil fortlaufende Filmphase bestimmt die
Endkante. Kurze Logo-Messaussetzer in echtem Film werden weiterhin toleriert.

Wichtig:
Bei WeDo arbeitet V4.1 zunächst mit grober Suche im 20-Sekunden-Raster und
lokaler Bestätigung. Reicht die lokale Suchabdeckung nicht aus, startet
automatisch die vollständige bisherige Analyse. Die WeDo-Intervalle bleiben
für innere Werbeblöcke autoritativ. Der separate WeDo-Teststarter wird nicht
mehr benötigt.
