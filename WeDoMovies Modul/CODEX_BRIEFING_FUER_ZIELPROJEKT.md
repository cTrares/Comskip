# Codex-Briefing für das WeDoMovies-Zielprojekt

## Auftrag

Analysiere die beigefügte Datei `LOGOFINDER_TECHNISCHE_UEBERGABE.md` und bewerte, wie die darin beschriebene Overlay-/Logo-Abwesenheitserkennung als zusätzliche, unabhängige Evidenzspur in dieses Projekt integriert werden kann.

Das Ziel ist nicht, LogoFinder als komplette Anwendung zu kopieren. Das Ziel ist, seine fachlichen Kerngedanken kontrolliert zu übernehmen:

1. optionaler manueller Fallback, bei dem ein Benutzer eine Logo-ROI vorgibt,
2. vollautomatische Ermittlung einer stabilen Overlay-ROI per Heatmap,
3. Aufbau einer robusten Overlay-Referenz,
4. Erzeugung einer Present-Score-Timeline,
5. Ableitung möglicher Werbeintervalle aus längerer Overlay-Abwesenheit,
6. Fusion dieser Evidenz mit den bereits vorhandenen Erkennungsverfahren des Zielprojekts.

## Verbindliche Zugriffsgrenze

Arbeite ausschließlich mit Dateien im aktuellen Zielprojekt bzw. mit Dateien, die der Benutzer dort ausdrücklich bereitstellt.

- Suche nicht selbstständig nach dem ursprünglichen LogoFinder-Ordner.
- Lies und verändere keine Dateien im ursprünglichen LogoFinder-Repository.
- Verwende keine absoluten Pfade, Netzwerkfreigaben, Symlinks oder andere Umgehungen, um auf LogoFinder zuzugreifen.
- Wenn Quellcode, ein Testvideo, eine Datenbankstruktur oder weitere Details fehlen, benenne die exakt benötigten Dateien und bitte den Benutzer, sie manuell in dieses Zielprojekt zu kopieren.
- Verändere zunächst keinen Produktivcode. Beginne mit einer Architektur- und Schnittstellenanalyse.
- Behandle beigefügte LogoFinder-Dateien als Referenzcode. Passe Persistenz, Jobs, Logging und UI an die Architektur dieses Zielprojekts an.

## Fachlich wichtige Unterscheidung

LogoFinder besitzt drei Fähigkeiten, die nicht vermischt werden dürfen:

- Der manuelle vorlagenbasierte Scan markiert ein Logo in einem Film und sucht im selben Film nach längerer Abwesenheit.
- Die automatische Overlay-Werbeblockerkennung findet ohne Vorwissen eine stabile Bildstruktur und sucht nach deren Abwesenheit.
- Die trainierte Logo-Bibliothek erkennt bekannte Logos in weiteren Filmen, erkennt dadurch allein aber noch keine Werbeblöcke.

Für eine erste Integration ist die vollautomatische Overlay-Werbeblockerkennung zu bevorzugen. Der manuelle Pfad soll als optionaler Fallback konzipiert werden. Die trainierte Bibliothek ist eine spätere Ausbaustufe.

## Erwartetes erstes Ergebnis

Liefere zunächst:

1. eine Karte der vorhandenen Werbeerkennungs-Pipeline dieses Zielprojekts,
2. den besten Integrationspunkt für eine neue `overlay_absence`-Evidenzspur,
3. eine vorgeschlagene, zustandsarme API,
4. ein Datenmodell für Overlay, Timeline-Punkte und alle Werbekandidaten,
5. eine Liste der LogoFinder-Referenzdateien, die für die konkrete Implementierung noch benötigt werden,
6. einen Testplan einschließlich Eigenwerbung mit sichtbarem Branding,
7. Risiken, Konflikte und offene Entscheidungen,
8. einen schrittweisen Implementierungsplan, noch ohne Änderungen am Produktivcode.

## Gewünschte technische Schnittstelle

Die Zielarchitektur sollte ungefähr folgende Verantwortungsgrenze besitzen:

```python
report = detect_ads_by_overlay(
    video_path,
    config=config,
    manual_rect=None,
    manual_template=None,
)
```

Der Report soll mindestens enthalten:

- erkannte oder manuell vorgegebene ROI,
- Overlay-Konfidenz,
- verwendete Sample-Zeiten,
- vollständige Present-Score-Timeline,
- alle vorgeschlagenen Werbeintervalle,
- minimale und mittlere Scores,
- Diagnose- und Versionsangaben,
- klare Fehler- und Timeout-Informationen.

## Entscheidungsregel

Behandle `overlay_absence` nicht als endgültiges Werbeurteil. Es ist ein erklärbares Signal, das mit den vorhandenen Erkennungsarten kombiniert werden soll. Eigenwerbung kann Senderbranding enthalten, während Filmsequenzen das Logo aus redaktionellen Gründen kurz verlieren können.

## Dateien, die zunächst genügen

- `LOGOFINDER_TECHNISCHE_UEBERGABE.md`
- optional `1.png`, `2.png`, `3.png`, `4.png`

Fordere erst danach gezielt einzelne Quellmodule an. Bitte niemals pauschal um das gesamte LogoFinder-Projekt oder dessen Laufzeitdaten.

## Hinweis zur Codex-Isolation

Codex arbeitet innerhalb der für den jeweiligen Task freigegebenen Arbeits- und Sandboxgrenzen. Ein Zielprojekt erhält nicht automatisch Wissen über oder Schreibzugriff auf ein anderes lokales Repository. Die sichere Übergabe besteht deshalb aus bewusst kopierten Dokumenten und ausgewählten Referenzdateien. Falls eine Aktion die freigegebenen Grenzen überschreiten würde, muss sie gesondert autorisiert werden.

Offizielle Hintergrundinformation: [OpenAI Docs – Codex Sandbox](https://learn.chatgpt.com/docs/sandboxing)
