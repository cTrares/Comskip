COMSKIP V4 - KOMMERZIELLER LOGO-MAKROMODUS
==========================================

V4 ist ein getrennter Entwicklungsfork auf Basis der gesicherten V3-Version.

Automatische Auswahl:
- Schnellmodus-Sender.txt   -> öffentlich-rechtlicher V3-Schnellmodus
- wedo-movies im Dateinamen -> eigener bestehender WeDo-Workflow
- Makromodus-Sender.txt     -> neuer kommerzieller Logo-Makromodus
- alle übrigen Dateien      -> bisherige vollständige Analyse

Der Makromodus wird deutlich im Konsolenfenster, im Log und in einer Datei
<Filmname>.makromodus.txt gekennzeichnet.

Sicherheitslogik und Prüfmarker:
- Kurze Logo-Aussetzer werden zuerst innerhalb eines stabilen Filmblocks
  repariert; erst danach wird über Film- und Werbeblöcke entschieden.
- Stabile positive Filmabschnitte werden nicht still als Werbung überdeckt.
- Orange Null-Längen-Marker begrenzen unsichere Logo-Rückkehrbereiche auf
  höchstens 120 Sekunden. M/N springt zu ihnen. Sie stehen nur in der TXT,
  niemals als Schnitt in der EDL.
- Die Markerübersicht liegt zusätzlich in <Filmname>.pruefmarker.txt.
- Am Blockrand in ComskipGUI die richtige Stelle suchen und B (Beginn) oder
  E (Ende) drücken; J/K sind nur flüchtige Vorher-/Nachher-Marker, L löscht sie.

Senderliste ändern:
Makromodus-Sender.txt mit einem Dateinamen-Token pro Zeile bearbeiten.

Vollständige Analyse für eine einzelne Aufnahme erzwingen:
comskip-final.exe --full-analysis "D:\Pfad\Film_sender_hq.mp4"

Makromodus vorübergehend abschalten:
comskip-final.exe --macro-mode off "D:\Pfad\Film_sender_hq.mp4"

Wichtig:
Der erste V4-Build dient dem gebündelten Vergleichslauf über den vorhandenen
kommerziellen Filmsatz. V3 bleibt separat erhalten und wird nicht überschrieben.
