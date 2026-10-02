# PromptInjectionFinder

*[English version: README.md](README.md)*

**Deterministischer, offline arbeitender Scanner für versteckte Prompt Injections in PDF-, Markdown-, Text- und HTML-Dateien sowie ganzen Webseiten (per Link inklusive Unterseiten) – mit Bereinigung und Export.**

Wer Text aus Webseiten, PDFs oder Dokumenten an ein KI-Modell weitergibt, gibt oft mehr weiter, als er sieht:
weißer Text auf weißem Grund, winzige oder verdeckte Schrift, unsichtbare Unicode-Zeichen, in Emojis versteckte Bytes,
HTML-Kommentare oder kodierte Befehle. PromptInjectionFinder macht genau diese Inhalte sichtbar, bewertet sie und
entfernt sie auf Wunsch.

- **Deterministisch:** keine KI, keine Heuristik mit Zufall. Gleiche Eingabe ergibt immer das gleiche Ergebnis, und jeder Fund ist mit Regel-ID begründet.
- **Offline:** Der Server läuft nur auf `127.0.0.1`, und es werden keine externen Ressourcen geladen.
- **Nachvollziehbar:** Jeder Fund zeigt Fundstelle, Begründung, dekodierten versteckten Inhalt und die Position im Dokument.
- **Englisch und Deutsch:** Die Oberfläche hat einen **EN/DE**-Umschalter (Standard: Englisch). Funde, Berichte und Exporte folgen der gewählten Sprache; in der Kommandozeile mit `--lang de` oder `PIF_LANG=de`.

---

> ⚠️ **Die Dateien in `samples/` enthalten absichtlich echte Prompt-Injection-Payloads** (dafür sind sie da).
> Nicht an einen KI-Agenten geben, der in deinem Namen handeln kann (E-Mails senden, Befehle ausführen, Dinge freigeben) –
> stattdessen mit diesem Tool scannen. Das gilt auch für die Angriffsphrasen in `pif/patterns.py` und in den Tests.

## Installation (ein Befehl)

**Windows** (PowerShell):

```powershell
irm https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.ps1 | iex
```

**Linux und macOS** (Terminal):

```bash
curl -fsSL https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.sh | sh
```

Der Installer:

- holt das neueste Release,
- legt eine eigene Python-Umgebung an,
- installiert die zwei Abhängigkeiten,
- richtet die Starter ein: überall den Befehl `pif` (Kommandozeile); unter Windows Desktop- und Startmenü-Verknüpfung
  (`pif` ist `bin\pif.cmd` im Installationsordner, eingetragen im *Benutzer*-PATH – ohne Adminrechte), unter
  Linux/macOS zusätzlich den Befehl `promptinjectionfinder` (Oberfläche) in `~/.local/bin`, unter Linux außerdem einen
  Startmenü-Eintrag.

Optionen (Umgebungsvariablen): `PIF_DIR` Installationsordner, `PIF_NO_SHORTCUTS=1` keine Verknüpfungen/Menüeinträge,
`PIF_NO_PATH=1` (Windows) Benutzer-PATH nicht ändern. Nach der Installation ein neues Terminal öffnen, damit `pif`
gefunden wird. Deinstallation unter Windows: `%LOCALAPPDATA%\PromptInjectionFinder`, die Verknüpfungen und den
`bin`-Eintrag im Benutzer-PATH löschen (*Umgebungsvariablen für dieses Konto bearbeiten*).

Fehlt Python, installiert ihn der Windows-Installer per `winget`; unter Linux/macOS nennt er den passenden Paketbefehl.
Ein **zweiter Aufruf aktualisiert** eine vorhandene Installation.

Ohne Installer (z. B. nach `git clone` oder ZIP-Download): einfach die Startskripte in der Tabelle unten benutzen.

> Die Einzeiler und das Update über die GitLab-API funktionieren ohne Anmeldung nur, wenn das GitLab-Projekt **öffentlich**
> ist. Bei einem privaten Projekt: `git clone https://gitlab.com/LuGG000/promptinjectionfinder.git` mit eigenem Zugang und
> dann `install.sh` / `install.ps1` im Ordner starten. Updates laufen dann über `git` mit denselben Zugangsdaten.
> Alternativ einen Token in `PIF_GITLAB_TOKEN` setzen.

## Update auf die neueste Version

| Weg | Befehl |
|---|---|
| Oberfläche | Knopf **⟳** oben rechts → „Jetzt aktualisieren“ |
| Windows | `pif update`, Startmenü „Update PromptInjectionFinder“ oder `update_windows.bat` |
| Linux / macOS | `pif update` oder `./update_linux_mac.sh` |
| Nur prüfen | `pif update --check` (Exit-Code 10 = neue Version verfügbar) |

Releases sind Git-Tags `vX.Y.Z`; die CI legt daraus automatisch ein GitLab-Release an. Ein Update holt das neueste Release:

- **Git-Installation:** per `git fetch` und Fast-Forward.
- **Sonst:** per Archiv-Download. Ersetzt werden nur die Programmdateien; eine Sicherung landet in `.update-backup`.

`.venv`, Exporte und eigene Dateien bleiben unberührt. Danach werden die Abhängigkeiten aktualisiert, und ein Neustart des
Programms genügt. Bei Installer-Installationen frischt der erste Start nach einem Update außerdem den Befehl `pif` auf
(so bekommen ihn auch ältere Installationen, z. B. unter Windows).

**Python-Upgrades:** Die eigene Umgebung gehört zu einer Python-Version. Ersetzt ein System-Upgrade sie (z. B.
Python 3.13 → 3.14 per `pacman -Syu` / `yay -Syu` oder `brew upgrade`, oder unter Windows wird das alte Python
deinstalliert), baut der nächste Start über `pif`, die Startskripte oder den Menüeintrag `.venv` automatisch neu auf
(einmalig mit Internet).

## Starten ohne Installer

Die Bedienung läuft komplett per Klick im Browser. Ein Startskript legt beim ersten Start eine eigene Umgebung (`.venv`)
an und installiert die zwei Abhängigkeiten. Danach läuft alles offline, und es wird nichts systemweit installiert.
Unter Windows legt der erste Start zusätzlich einen Startmenü-Eintrag „PromptInjectionFinder“ für diesen Ordner an (damit
die Windows-Suche ihn findet; entfällt, wenn schon einer existiert, oder mit `PIF_NO_SHORTCUTS=1`). Den globalen Befehl
`pif` richtet nur der Installer ein.

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
2. Links erscheint jede Datei mit Bewertung (*Gefährlich*, *Verdächtig*, *Unauffällig*). Die Dateien eines Scans
   (Website, Ordner, Upload) stehen gruppiert unter Start-URL bzw. Ordner; der neueste Scan ist aufgeklappt, ältere
   klappen zu, und das **×** an einer Gruppe entfernt den ganzen Scan.
3. **Funde:** Jeder Fund hat eine Checkbox. Empfohlene Funde sind vorausgewählt.
   **Dokument:** Bei Text, Markdown und HTML wird die Fundstelle farbig markiert und unsichtbare Zeichen erscheinen als Chips.
   Bei PDFs wird die gerenderte Seite angezeigt, und rote Rahmen zeigen den unsichtbaren Text.
   **Bereinigte Vorschau:** zeigt das Ergebnis der Bereinigung samt neuer Risikobewertung.
4. **Bereinigt herunterladen** liefert eine einzelne Datei. **Bereinigen & exportieren** bietet zwei Wege:
   - **ZIP herunterladen:** Alle bereinigten Dateien landen samt `report.html` und `report.json` im Download-Ordner des Browsers.
   - **In Ordner speichern:** schreibt in einen frei wählbaren Ordner und öffnet ihn auf Wunsch im Dateimanager.

   Die Originale bleiben unverändert.

### Webseiten scannen (per Link)

Über **Webseite scannen** gibst du eine URL ein. Das Programm lädt die Seite und folgt auf Wunsch den Links und Unterseiten.

- **Link-Tiefe:** 0 = nur diese Seite, 1 = plus die dort verlinkten Seiten, 2 = plus die von dort verlinkten, … Dazu
  kommt ein Limit für die Seitenzahl, standardmäßig 30. Die Tiefe zählt Link-*Ebenen*, nicht Seiten.
- **Nur Seiten unterhalb dieser Adresse** ist voreingestellt: Ab `…/wiki/Installation` werden nur `…/wiki/…`-Seiten
  verfolgt, nicht die Navigation der ganzen Website (verlinkte Dokumente werden weiterhin geladen). CLI: `--all-paths`
  schaltet das ab.
- Seiten werden analysiert, während die nächsten noch laden; mit JavaScript kostet das Laden/Rendern die meiste Zeit
  (etwa 5 s pro Seite) – für statische Seiten abschalten, dann geht es schneller.
- **Nur dieselbe Domain** ist voreingestellt; **robots.txt** wird beachtet. Beides lässt sich für eigene Seiten abschalten.
- **Verlinkte Dokumente** (PDF, TXT, MD, …) und **iframes** werden mitgeladen und mitgescannt.
- **Externe Stylesheets** werden mitgeladen, inklusive CSS-Variablen und Farbverläufen. Nur so wird Text erkannt, der über eine CSS-Klasse
  versteckt ist. `@media print` und Mobil-Regeln werden ignoriert.
- **Reiter, Unterseiten und Aufklappbereiche**, die per CSS-Zustand (`.page.active`, `:target`, …) oder per Skript umgeschaltet werden,
  zählen als normaler Inhalt und nicht als „versteckt“. Versteckte Elemente *innerhalb* solcher Reiter werden trotzdem gefunden.
- Optional: **im Text/in Kommentaren erwähnte Dateien ausprobieren**, z. B. `vorlage.html` aus einem HTML-Kommentar.
- Seiten mit identischem Inhalt werden nur einmal gescannt, und ein Protokoll zeigt jede URL mit Status (geladen, 404, robots, Duplikat).

**JavaScript:** Ist Chrome, Edge, Chromium oder Brave installiert, wird jede Seite zusätzlich wie im Browser dargestellt
(headless, `--dump-dom`). So sind auch Inhalte enthalten, die erst per Skript entstehen, etwa generierte Aufgaben oder Reiter.
Geprüft wird die dargestellte Seite *und* der ausgelieferte Quelltext. Was nur im Quelltext steht (Scraper und KI-Tools lesen es
trotzdem), wird als „Nur im Seitenquelltext“ gemeldet. Ohne Browser wird das statische HTML genutzt. Das Scannen von Webseiten
ist die einzige Funktion, die das Internet nutzt.

**Export von Webseiten: Text und Aufgaben statt HTML.** Für jede Seite entsteht eine Markdown-Datei mit dem bereinigten Text in
Anzeige-Reihenfolge:

- Überschriften, Listen und Tabellen bleiben erhalten. Eingabefelder erscheinen als `____`, Beschriftungen von Grafiken/Schaltbildern
  als `[Grafik: …]`, Reiter und Unterseiten mit ihrem Namen.
- Echt versteckter Text, also Injections, fehlt. Inhalte, die erst nach einem Klick sichtbar werden (Tipp, Lösung, `<details>`),
  sind als *aufklappbar* markiert.
- Oben stehen die **erkannten Aufgaben**: Überschriften wie „Aufgabe 1.2“ oder „Fragen zur Sicherung“, Eingabefelder und
  Lückentabellen, Arbeitsanweisungen mit Operatoren (berechne/berechnet/berechnen Sie, erkläre, beschreibt, …), Fragenlisten,
  vorhandene Lösung/Tipp. Navigation und Fußzeile zählen nicht zu Aufgaben.
- Zusätzlich entstehen `Webseiten_Text_gesamt.md` (alle Seiten in Crawl-Reihenfolge) und `Aufgaben_gesamt.md`
  (im englischen Modus: `Website_text_all.md`, `Tasks_all.md`).

```bash
python -m pif scan-url https://beispiel.de/ --depth 2 --max-pages 50 --discover --out export/
```

### Kommandozeile

```bash
python -m pif scan samples/ -v                 # Bericht in der Konsole
python -m pif scan datei.pdf --json            # maschinenlesbar
python -m pif --lang de scan samples/          # Ausgabe auf Deutsch (Standard: Englisch)
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

### Injection-Sprache (≈ 110 Regeln)
Die Regeln decken Anweisungs-Überschreibung, Rollenübernahme und Jailbreaks, Systemprompt-Ausspähung, gefälschte Chat-Marker
(`<|im_start|>`, `[INST]`, `<<SYS>>`), direkte KI-Ansprache („Hinweis an die KI“), Verschleierung („sag dem Nutzer nichts“),
Exfiltration, Befehlsausführung und Bewertungsmanipulation ab (z. B. „give a positive review“ in Lebensläufen und Papern).
Alle zehn Kategorien sind auf **Englisch** (56 Regeln) und **Deutsch** (38 Regeln) abgedeckt; für Französisch, Spanisch,
Italienisch, Portugiesisch und Niederländisch gibt es nur die Kernregel „ignoriere alle vorherigen Anweisungen“.
Sprachunabhängige Regeln (Chat-Marker, gefährliche Shell-Befehle) gelten für jeden Text.

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
| PDF | Versteckter Text wird per Redaction *ohne sichtbare Box* aus dem Inhaltsstrom entfernt. Annotationen, Links, Metadaten, JavaScript- und Launch-Aktionen sowie eingebettete Dateien werden entfernt. Zusätzlich wird eine `.bereinigt.txt` (englisch: `.cleaned.txt`) mit dem sauberen Textinhalt exportiert. |

Nach jeder Bereinigung wird die Datei erneut gescannt, und der Bericht zeigt das Risiko vorher und nachher.

> Hinweis zu PDFs: Liegt versteckter Text exakt *unter* sichtbarem Text, entfernt die Redaction an dieser Stelle beides.
> In der Vorschau ist das sofort zu sehen.

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Die Suite umfasst über 190 Tests: Angriffe auf Englisch, Deutsch und in 5 weiteren Sprachen, 11 Verschleierungsarten, harmlose Gegenbeispiele,
alle Smuggling-Techniken, 10 PDF-Versteckvarianten inklusive gedrehter Seiten und OCR-Scans, Bereinigung mit
verschiedenen Kodierungen, Export und die Web-API inklusive Token- und DNS-Rebinding-Schutz.
`tools/make_samples.py` erzeugt die Demo-Dateien in `samples/`.

End-to-End-Test der Oberfläche: Chrome wird über das DevTools-Protokoll gesteuert, ohne zusätzliche Abhängigkeiten.
Voraussetzungen sind Node ≥ 22 und Chrome:

```bash
python -m pif gui --no-browser --port 8812 &
node tests/ui_e2e.mjs http://127.0.0.1:8812/ "<pfad>\samples\attack_recipe.md,<pfad>\samples\attack_cv.pdf" "<export-ordner>"
```

Für die Regelbasis wurden harmlose Dateien als Fehlalarm-Benchmark genutzt (≈ 4.500 Dateien aus npm-Doku, der
Python-Standardbibliothek, pip/numpy und einer HTML-Hilfe mit 2.500 Seiten): 4 von 4.522 Dateien (0,1 %) werden als
*verdächtig* eingestuft, keine als *gefährlich*.

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
samples/               Demo-Dateien (attack_* / benign_*, deutsch und englisch)
```

## Lizenz

Copyright (C) 2026 LuGG000

PromptInjectionFinder ist freie Software unter der **GNU Affero General Public License v3.0 oder später**
(AGPL-3.0-or-later), siehe [LICENSE](LICENSE). Die Software wird ohne jede Gewährleistung bereitgestellt.

Warum AGPL: Die PDF-Analyse nutzt [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (© Artifex, AGPL-3.0 oder kommerzielle
Lizenz), das auch in der EXE enthalten ist. Weitere Komponenten: [NumPy](https://numpy.org) (BSD-3-Clause) und in der EXE die
Python-Laufzeit (PSF-Lizenz). Wer veränderte Versionen weitergibt – auch als Netzwerkdienst –, muss den Quellcode unter
derselben Lizenz zugänglich machen. (Rechtlich verbindlich ist der englische Lizenztext in `LICENSE`.)
