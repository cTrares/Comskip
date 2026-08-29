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

Senderliste ändern:
Makromodus-Sender.txt mit einem Dateinamen-Token pro Zeile bearbeiten.

Vollständige Analyse für eine einzelne Aufnahme erzwingen:
comskip-final.exe --full-analysis "D:\Pfad\Film_sender_hq.mp4"

Makromodus vorübergehend abschalten:
comskip-final.exe --macro-mode off "D:\Pfad\Film_sender_hq.mp4"

Wichtig:
Der erste V4-Build dient dem gebündelten Vergleichslauf über den vorhandenen
kommerziellen Filmsatz. V3 bleibt separat erhalten und wird nicht überschrieben.
