# PromptInjectionFinder

**Deterministischer, vollständig offline arbeitender Scanner für versteckte Prompt Injections in PDF-, Markdown-, Text- und HTML-Dateien – mit Bereinigung und Export.**

Wer Text aus Webseiten, PDFs oder Dokumenten an ein KI-Modell weitergibt, gibt oft mehr weiter, als er sieht:
weißer Text auf weißem Grund, winzige oder verdeckte Schrift, unsichtbare Unicode-Zeichen, in Emojis versteckte Bytes,
HTML-Kommentare oder kodierte Befehle. PromptInjectionFinder macht genau diese Inhalte sichtbar, bewertet sie und
entfernt sie auf Wunsch.

- **Deterministisch:** keine KI, keine Heuristik mit Zufall. Gleiche Eingabe ergibt immer das gleiche Ergebnis, und jeder Fund ist mit Regel-ID begründet.
- **Offline:** Der Server läuft nur auf `127.0.0.1`, und es werden keine externen Ressourcen geladen.
- **Nachvollziehbar:** Jeder Fund zeigt Fundstelle, Begründung, dekodierten versteckten Inhalt und die Position im Dokument.

---

## Schnellstart

Die Bedienung läuft komplett per Klick im Browser. Ein Startskript legt beim ersten Start eine eigene Umgebung (`.venv`)
an und installiert die zwei Abhängigkeiten. Danach läuft alles offline, und es wird nichts systemweit installiert.

| System | Starten | Voraussetzung |
|---|---|---|
| **Windows** 10/11 | Doppelklick auf **`run_windows.bat`** | Python ≥ 3.9 von python.org (Haken „Add to PATH“) oder `winget install Python.Python.3.12` |
| **macOS** (Intel & Apple Silicon) | Doppelklick auf **`run_mac.command`** (beim ersten Mal: Rechtsklick → Öffnen) | `brew install python` oder python.org |
| **Debian / Ubuntu / Mint** | `./run_linux_mac.sh` | `sudo apt install python3 python3-venv` |
| **Arch / Manjaro** | `./run_linux_mac.sh` | `sudo pacman -S python` |
| **Fedora / openSUSE** | `./run_linux_mac.sh` | `sudo dnf install python3` bzw. `sudo zypper install python3` |
| **Windows ohne Python** | `PromptInjectionFinder.exe` (siehe unten) | – |

Der Browser öffnet sich automatisch unter `http://127.0.0.1:8765`. Das Terminalfenster muss offen bleiben, denn es ist der
lokale Server; Schließen beendet das Programm. Ist der Port belegt, wird automatisch der nächste freie genommen.

Manuell, falls gewünscht:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python -m pif                                              # startet die Oberfläche
```

### Weboberfläche

1. Dateien oder ganze Ordner per Drag & Drop ablegen, über **Dateien wählen** / **Ordner hochladen** auswählen
   oder per **Pfad scannen** einen lokalen Ordner angeben.
2. Links erscheint jede Datei mit Bewertung (*Gefährlich*, *Verdächtig*, *Unauffällig*).
3. **Funde:** Jeder Fund hat eine Checkbox. Empfohlene Funde sind vorausgewählt.
   **Dokument:** Bei Text, Markdown und HTML wird die Fundstelle farbig markiert und unsichtbare Zeichen erscheinen als Chips.
   Bei PDFs wird die gerenderte Seite angezeigt, und rote Rahmen zeigen den unsichtbaren Text.
   **Bereinigte Vorschau:** zeigt das Ergebnis der Bereinigung samt neuer Risikobewertung.
4. **Bereinigt herunterladen** liefert eine einzelne Datei. **Bereinigen & exportieren** bietet zwei Wege:
   - **ZIP herunterladen:** Alle bereinigten Dateien landen samt `report.html` und `report.json` im Download-Ordner des Browsers.
   - **In Ordner speichern:** schreibt in einen frei wählbaren Ordner und öffnet ihn auf Wunsch im Dateimanager.

   Die Originale bleiben unverändert.

### Kommandozeile

```bash
python -m pif scan samples/ -v                 # Bericht in der Konsole
python -m pif scan datei.pdf --json            # maschinenlesbar
python -m pif clean ordner/ --out export/      # bereinigen + exportieren
python -m pif gui samples/ --port 8765         # Oberfläche mit vorgeladenen Dateien
```

`scan` beendet sich mit Exit-Code 1, sobald eine Datei das Risiko 65 erreicht (`--fail-at`). Damit eignet sich der Befehl für CI-Pipelines.

---

## Was erkannt wird

### PDF (Analyse des *gerenderten* Dokuments)
| Technik | Wie sie erkannt wird |
|---|---|
| Weiße/hellgraue Schrift auf weißem Grund | Die Seite wird gerendert, und die Textfarbe wird gegen die tatsächlich gerenderte Hintergrundfarbe gemessen (WCAG-Kontrast). So werden auch farbige Kästen berücksichtigt, z. B. blau auf blau. |
| Winzige oder gestauchte Schrift | Schriftgröße, Glyphenhöhe und Zeichenbreite |
| Unsichtbarer Rendermodus (Tr 3), Transparenz | Texttrace-Rendermodus und Opazität |
| Text außerhalb der Seite | Text-Bounding-Box gegen den sichtbaren Seitenbereich (CropBox) |
| Text unter Bildern oder Flächen | Zeichenreihenfolge (Z-Order) plus deckende Flächen und Bilder, auch wenn darüber anderer Text steht |
| Abgeschnittener Text | Die Glyphenfarbe kommt im Rendering nicht vor |
| Annotationen, Formularfelder, Links, Metadaten/XMP, JavaScript, Launch-Aktionen, eingebettete Dateien | Objekt- und Inhaltsanalyse |
| Text auf ausgeblendeten Ebenen (Optional Content) | Analyse mit allen Ebenen eingeschaltet – andere PDF-Bibliotheken extrahieren diesen Text nämlich trotzdem |
| Kontur- und Füllungs-Text | deckungsgleiche Spans (z. B. weiße Füllung mit schwarzer Kontur) werden zusammen bewertet und nicht doppelt gezählt |
| OCR-Textebenen (Scans) | werden erkannt und *nicht* als versteckt gewertet; Injection-Text darin wird trotzdem gemeldet |

### Markdown / HTML
CSS-versteckte Elemente werden erkannt: `display:none`, `visibility:hidden`, `opacity`, `font-size:0`, weiße oder
hintergrundgleiche Schrift, `left:-9999px`, `clip`, `transform:scale(0)`, `height:0`, das `hidden`-Attribut, `<template>` sowie
Klassen-Regeln aus `<style>` mit echtem Selektor-Matching. Dazu kommen HTML-Kommentare, `[//]: # (…)`-Kommentare,
Front-Matter, Alt-Texte und Titel, LaTeX-Tricks (`\textcolor{white}`, `\phantom`), Exfiltrations-Bild-URLs
(`![](https://x/?q={chat})`) und `javascript:`-Links. Code-Blöcke werden korrekt als sichtbar behandelt.

### Unicode- und Emoji-Smuggling (alle Formate)
- **Unicode-Tag-Zeichen** (ASCII-Smuggling, U+E0000–E007F). Sie werden dekodiert, legitime Flaggen wie 🏴󠁧󠁢󠁥󠁮󠁧󠁿 bleiben erlaubt.
- **Variation-Selector-Smuggling** („Text in Emojis“): Bytes, die an ein Emoji angehängt sind, werden dekodiert.
- **Zero-Width-Steganografie** (binär kodierte Nachrichten) und Zero-Width-Zeichen, die Wörter zerteilen.
  Legitime Fälle wie Emoji-ZWJ-Sequenzen oder persische ZWNJ werden ignoriert.
- **Bidi-Overrides** (Trojan Source), Steuerzeichen, ANSI-Escape-Codes (inklusive `ESC[8m` Conceal) und Wagenrücklauf-Überschreibung.
- **Homoglyphen** (kyrillisch/griechisch in lateinischen Wörtern). Beim Bereinigen werden sie durch die echten Buchstaben ersetzt.
- **Stilisierte Buchstaben:** 𝐟𝐞𝐭𝐭, Ｖｏｌｌｂｒｅｉｔｅ, 🅴🅼🅾🅹🅸-Buchstaben, Regional-Indicator-Text, Zalgo.

### Kodierte Payloads
Base64, Hex, `\x..`, `\u....`, URL-Encoding, HTML-Entities, Binär, ROT13 und rückwärts geschriebener Text werden dekodiert
und erneut gegen die Regelbasis geprüft.

### Injection-Sprache (≈ 110 Regeln, 7 Sprachen)
Die Regeln decken Anweisungs-Überschreibung, Rollenübernahme und Jailbreaks, Systemprompt-Ausspähung, gefälschte Chat-Marker
(`<|im_start|>`, `[INST]`, `<<SYS>>`), direkte KI-Ansprache („Hinweis an die KI“), Verschleierung („sag dem Nutzer nichts“),
Exfiltration, Befehlsausführung und Bewertungsmanipulation ab (z. B. „give a positive review“ in Lebensläufen und Papern).
Unterstützt werden Deutsch, Englisch, Französisch, Spanisch, Italienisch, Portugiesisch und Niederländisch.

Die Regeln laufen auf einer **normalisierten Sicht** des Textes. Dabei werden Homoglyphen gefaltet, Akzente entfernt,
unsichtbare Zeichen ignoriert, Leetspeak (`1gn0r3`) und g e s p e r r t e Buchstaben zusammengeführt. Über eine Offset-Tabelle
zeigt jeder Treffer exakt auf die Originalstelle. Gegen Fehlalarme helfen strikte Wortgrenzen, wobei Matches ohne Leerzeichen
nur in nachweislich verschleierten Bereichen zugelassen werden, außerdem ein Negations-Filter („never share your password“)
und Clusterbildung: Erst mehrere schwache Signale zusammen ergeben einen starken Fund.

### Bewertung
Jeder Fund hat einen Score von 0–100 (*Info* < 20 ≤ *Niedrig* < 40 ≤ *Mittel* < 65 ≤ *Hoch* < 85 ≤ *Kritisch*).
Versteckter Inhalt, der zusätzlich Injection-Sprache enthält, wird hochgestuft. Das Dateirisiko ergibt sich aus dem stärksten
Fund plus einem gedämpften Anteil weiterer *unterschiedlicher* Signale. Wiederholungen derselben Regel addieren sich nicht.

---

## Bereinigung

| Dateityp | Vorgehen |
|---|---|
| Text, Markdown, HTML | Ausgewählte Bereiche werden zeichengenau entfernt (ganze Sätze oder Elemente). Homoglyphen und stilisierte Buchstaben werden ersetzt statt gelöscht. Die Kodierung (UTF-8/BOM, UTF-16, cp1252) und Zeilenenden bleiben erhalten. |
| PDF | Versteckter Text wird per Redaction *ohne sichtbare Box* aus dem Inhaltsstrom entfernt. Annotationen, Links, Metadaten, JavaScript- und Launch-Aktionen sowie eingebettete Dateien werden entfernt. Zusätzlich wird eine `.bereinigt.txt` mit dem sauberen Textinhalt exportiert. |

Nach jeder Bereinigung wird die Datei erneut gescannt, und der Bericht zeigt das Risiko vorher und nachher.

> Hinweis zu PDFs: Liegt versteckter Text exakt *unter* sichtbarem Text, entfernt die Redaction an dieser Stelle beides.
> In der Vorschau ist das sofort zu sehen.

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Die Suite umfasst über 150 Tests: Angriffe in 7 Sprachen, 11 Verschleierungsarten, harmlose Gegenbeispiele,
alle Smuggling-Techniken, 10 PDF-Versteckvarianten inklusive gedrehter Seiten und OCR-Scans, Bereinigung mit
verschiedenen Kodierungen, Export und die Web-API inklusive Token- und DNS-Rebinding-Schutz.
`tools/make_samples.py` erzeugt die Demo-Dateien in `samples/`.

End-to-End-Test der Oberfläche: Chrome wird über das DevTools-Protokoll gesteuert, ohne zusätzliche Abhängigkeiten.
Voraussetzungen sind Node ≥ 22 und Chrome:

```bash
python -m pif gui --no-browser --port 8812 &
node tests/ui_e2e.mjs http://127.0.0.1:8812/ "<pfad>\samples\angriff_rezept.md,<pfad>\samples\angriff_lebenslauf.pdf" "<export-ordner>"
```

Für die Regelbasis wurden zwei Korpora harmloser Dateien als Fehlalarm-Benchmark genutzt: rund 1.500 Dateien aus npm
(Doku, Markdown, HTML, JS) und rund 500 aus der Python-Standardbibliothek, pip und numpy. Dort liegt die Fehlalarmquote
der Stufe *Verdächtig* bei unter 1 %.

## Plattform-Tests

`.gitlab-ci.yml` startet das Tool bei jedem Push genau so, wie ein Nutzer es tut (`run_linux_mac.sh`), und führt danach
die komplette Test-Suite aus. Das passiert auf Debian 12, Ubuntu 24.04, Arch Linux und Fedora sowie mit Python 3.9 und 3.13.
Windows wird lokal getestet (Suite, Startskript, EXE, Browser-E2E). macOS nutzt dasselbe Startskript wie Linux.
PyMuPDF und numpy liefern fertige Pakete für macOS (Intel und Apple Silicon); mangels Mac-Runner gibt es dort aber keinen automatischen Test.

## Eigenständige EXE (optional)

```bat
tools\build_exe.bat
```

Erzeugt mit PyInstaller `dist\PromptInjectionFinder.exe`, die ohne Python-Installation läuft.

## Sicherheit der Oberfläche
Der lokale Server bindet ausschließlich an `127.0.0.1`. Jede API-Anfrage braucht ein zufälliges Sitzungs-Token, und der Host-Header
wird geprüft (Schutz gegen DNS-Rebinding). Eine strikte Content-Security-Policy verhindert, dass andere Webseiten im Browser die lokale
API steuern können.

## Projektstruktur
```
pif/
  patterns.py          Regelbasis + Matching-Engine
  normalize.py         normalisierte Textsichten mit Offset-Mapping
  unicode_tools.py     Zeichenklassen, Smuggling-Decoder, Homoglyphen
  text_analyzer.py     formatunabhängige Analyse
  markup_analyzer.py   Markdown/HTML-Versteckanalyse
  css.py               Farben, Kontrast, CSS-Versteckregeln
  pdf_analyzer.py      PDF-Sichtbarkeitsanalyse
  scanner.py           Dateityp-Erkennung, Zusammenführung
  cleaner.py           Bereinigung + Export
  report.py            HTML-Bericht
  server.py, web/      Offline-Weboberfläche
tests/                 pytest-Suite
tools/                 Beispiel-Generator, EXE-Build
samples/               Demo-Dateien (angriff_* / harmlos_*)
```
