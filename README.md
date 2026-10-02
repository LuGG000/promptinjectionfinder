# PromptInjectionFinder

*[Deutsche Version: README.de.md](README.de.md)*

**A deterministic, offline scanner for hidden prompt injections in PDF, Markdown, text and HTML files and whole websites (by link, including sub-pages) – with cleaning and export. Interface and reports in English and German.**

Whoever passes text from websites, PDFs or documents to an AI model often passes on more than they can see:
white text on white, tiny or covered text, invisible Unicode characters, bytes hidden in emojis, HTML comments or
encoded commands. PromptInjectionFinder makes exactly this content visible, rates it and removes it on request.

- **Deterministic:** no AI, no randomness. The same input always gives the same result, and every finding names the rule that produced it.
- **Offline:** the server only listens on `127.0.0.1` and loads no external resources.
- **Traceable:** every finding shows the evidence, the reason, the decoded hidden content and its position in the document.
- **English and German:** the rule base fully covers English and German (the core “ignore previous instructions” pattern
  also French, Spanish, Italian, Portuguese and Dutch). The interface has an **EN/DE** switch; findings, reports and
  exports follow the chosen language.

---

> ⚠️ **The files in `samples/` contain real prompt injection payloads on purpose** (that is what they are for).
> Do not hand them to an AI agent that can act on your behalf (send e-mails, run commands, approve things) –
> scan them with this tool instead. The same applies to the attack phrases in `pif/patterns.py` and the tests.

## Installation (one command)

**Windows** (PowerShell):

```powershell
irm https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.ps1 | iex
```

**Linux and macOS** (terminal):

```bash
curl -fsSL https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.sh | sh
```

The installer:

- fetches the newest release,
- creates a private Python environment,
- installs the two dependencies,
- sets up launchers: the command `pif` (command line) everywhere; on Windows a desktop and start menu shortcut
  (`pif` is `bin\pif.cmd` in the install folder, added to the *user* PATH – no admin rights), on Linux/macOS also the
  command `promptinjectionfinder` (interface) in `~/.local/bin`, on Linux also a menu entry.

Options (environment variables): `PIF_DIR` install folder, `PIF_NO_SHORTCUTS=1` no shortcuts / menu entries,
`PIF_NO_PATH=1` (Windows) leave the user PATH alone. Open a new terminal after installing so `pif` is found.
Uninstall on Windows: delete `%LOCALAPPDATA%\PromptInjectionFinder`, the shortcuts and its `bin` entry in the user PATH
(*Edit environment variables for your account*).

If Python is missing, the Windows installer installs it with `winget`; on Linux/macOS it shows the right package command.
**Running it a second time updates** an existing installation.

Without the installer (e.g. after `git clone` or a ZIP download): just use the start scripts in the table below.

> The one-liners and updates through the GitLab API only work without login if the GitLab project is **public**.
> For a private project: `git clone https://gitlab.com/LuGG000/promptinjectionfinder.git` with your own access, then run
> `install.sh` / `install.ps1` in that folder. Updates then use `git` with the same credentials.
> Alternatively set a token in `PIF_GITLAB_TOKEN`.

## Updating to the newest version

| Way | Command |
|---|---|
| Interface | **⟳** button at the top right → “Update now” |
| Windows | `pif update`, start menu “Update PromptInjectionFinder” or `update_windows.bat` |
| Linux / macOS | `pif update` or `./update_linux_mac.sh` |
| Check only | `pif update --check` (exit code 10 = new version available) |

Releases are git tags `vX.Y.Z`; the CI turns them into GitLab releases automatically. An update fetches the newest release:

- **git installation:** via `git fetch` and fast-forward.
- **otherwise:** by downloading the release archive. Only program files are replaced; a backup goes to `.update-backup`.

`.venv`, exports and your own files stay untouched. Afterwards the dependencies are updated; restart the program.
For installer installations the first start after an update also refreshes the `pif` command (so older installations
get it too, e.g. on Windows).

**Python upgrades:** the private environment belongs to one Python version. If a system upgrade replaces it (e.g.
Python 3.13 → 3.14 via `pacman -Syu` / `yay -Syu` or `brew upgrade`, or the old Python is uninstalled on Windows),
the next start via `pif`, the start scripts or the menu entry recreates `.venv` automatically (needs internet once).

## Starting without the installer

Everything is operated by clicking in the browser. A start script creates a private environment (`.venv`) on the first
start and installs the two dependencies. After that everything runs offline and nothing is installed system-wide.
On Windows the first start also adds a start menu entry “PromptInjectionFinder” for this folder (so Windows search finds
it; skipped if one exists or with `PIF_NO_SHORTCUTS=1`). The global `pif` command is only set up by the installer.

| System | Start | Requirement |
|---|---|---|
| **Windows** 10/11 | double-click **`run_windows.bat`** | Python ≥ 3.9 from python.org (tick “Add to PATH”) or `winget install Python.Python.3.12` |
| **macOS** (Intel & Apple Silicon) | double-click **`run_mac.command`** (first time: right-click → Open) | `brew install python` or python.org |
| **Debian / Ubuntu / Mint** | `./run_linux_mac.sh` | `sudo apt install python3 python3-venv` |
| **Arch / Manjaro** | `./run_linux_mac.sh` | `sudo pacman -S python` |
| **Fedora / openSUSE** | `./run_linux_mac.sh` | `sudo dnf install python3` or `sudo zypper install python3` |
| **Windows without Python** | `PromptInjectionFinder.exe` (see below) | – |

The browser opens automatically at `http://127.0.0.1:8765`. Keep the terminal window open – it is the local server;
closing it quits the program. If the port is taken, the next free one is used.

Manually, if you prefer:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python -m pif                                              # starts the interface
```

### Web interface

1. Drop files or whole folders, use **Choose files** / **Upload folder**, or enter a local folder via **Scan path**.
2. Each file appears on the left with a verdict (*Dangerous*, *Suspicious*, *Clean*). The files of one scan (website,
   folder, upload) are grouped under the start URL or folder; the newest scan is unfolded, older ones fold away, and the
   **×** on a group removes that whole scan.
3. **Findings:** every finding has a checkbox; recommended ones are preselected.
   **Document:** for text, Markdown and HTML the evidence is highlighted and invisible characters appear as chips;
   for PDFs the rendered page is shown and red frames mark the invisible text.
   **Cleaned preview:** shows the result of the cleaning with the new risk rating.
4. **Download cleaned** gives you a single file. **Clean & export** offers two ways:
   - **Download ZIP:** all cleaned files plus `report.html` and `report.json` land in the browser's download folder.
   - **Save to folder:** writes into a folder of your choice and can open it in the file manager.

   The originals stay unchanged. The **EN/DE** button switches the language of the interface, the findings and the exports.

### Scanning websites (by link)

**Scan website** takes a URL. The program loads the page and, if you want, follows its links and sub-pages.

- **Link depth:** 0 = this page only, 1–3 = follow links; plus a page limit (default 30).
- **Same domain only** is preset and **robots.txt** is respected; both can be switched off for your own sites.
- **Linked documents** (PDF, TXT, MD, …) and **iframes** are loaded and scanned as well.
- **External stylesheets** are loaded too, including CSS variables and gradients – only then is text hidden via a CSS
  class detected. `@media print` and mobile-only rules are ignored.
- **Tabs, sub-pages and collapsible sections** toggled by a CSS state (`.page.active`, `:target`, …) or by script count as
  normal content, not as “hidden”. Hidden elements *inside* such tabs are still found.
- Optional: **try files mentioned in text/comments**, e.g. `template.html` from an HTML comment.
- Pages with identical content are scanned once; a log shows every URL with its status (loaded, 404, robots, duplicate).

**JavaScript:** if Chrome, Edge, Chromium or Brave is installed, every page is additionally rendered like in a browser
(headless, `--dump-dom`), so content created by scripts – generated exercises, tabs – is included. Both the rendered page
*and* the delivered source code are checked; anything that only exists in the source (scrapers and AI tools still read it)
is reported as “Only in page source”. Without a browser the static HTML is used. Scanning websites is the only feature that
uses the internet.

**Exporting web pages: text and tasks instead of HTML.** For every page a Markdown file with the cleaned text in display
order is written:

- Headings, lists and tables are kept; input fields appear as `____`, labels of graphics/circuit diagrams as
  `[Graphic: …]`, tabs and sub-pages with their names.
- Really hidden text (injections) is left out. Content that only appears after a click (hint, solution, `<details>`) is
  marked as *collapsible*.
- At the top are the **detected tasks**: headings like “Task 1.2”, “Aufgabe 1.2” or “Questions”, input fields and fill-in
  tables, work instructions with operator verbs (calculate, explain, describe / berechne, erkläre, beschreibt, …), question
  lists, an available solution/hint. Navigation and footer never count as tasks.
- Additionally `Website_text_all.md` (all pages in crawl order) and `Tasks_all.md` are written
  (German mode: `Webseiten_Text_gesamt.md`, `Aufgaben_gesamt.md`).

```bash
pif scan-url https://example.com/ --depth 2 --max-pages 50 --discover --out export/
```

### Command line

```bash
pif scan samples/ -v                     # report in the console
pif --lang de scan samples/              # German output
pif scan file.pdf --json                 # machine-readable (both languages in the "i18n" field)
pif clean folder/ --out export/          # clean + export
pif gui samples/ --port 8765             # interface with preloaded files
```

(Without the installer use `python -m pif …`.) `scan` exits with code 1 as soon as a file reaches risk 65 (`--fail-at`),
which makes it usable in CI pipelines. The default language can also be set with the environment variable `PIF_LANG=de`.

---

## What is detected

### PDF (analysis of the *rendered* document)
| Technique | How it is detected |
|---|---|
| White/light grey text on white | The page is rendered and the text colour is measured against the actually rendered background (WCAG contrast) – coloured boxes count too, e.g. blue on blue. |
| Tiny or squashed text | font size, glyph height and character width |
| Invisible render mode (Tr 3), transparency | text trace render mode and opacity |
| Text outside the page | text bounding box vs. the visible page area (CropBox) |
| Text under images or shapes | drawing order (z-order) plus opaque shapes/images, even if other text is drawn on top |
| Clipped text | the glyph colour does not occur in the rendering |
| Annotations, form fields, links, metadata/XMP, JavaScript, launch actions, embedded files | object and content analysis |
| Text on hidden layers (optional content) | analysed with all layers switched on – other PDF libraries extract it anyway |
| Outline/fill text | congruent spans (e.g. white fill with black outline) are rated together and counted once |
| OCR text layers (scans) | recognised and *not* counted as hidden; injection text inside is still reported |

### Markdown / HTML
CSS-hidden elements: `display:none`, `visibility:hidden`, `opacity`, `font-size:0`, white or background-coloured text,
`left:-9999px`, `clip`, `transform:scale(0)`, `height:0`, the `hidden` attribute, `<template>` and class rules from
`<style>`/external stylesheets with real selector matching. Plus HTML comments, `[//]: # (…)` comments, front matter,
alt texts, titles and `data-*` tooltips, LaTeX tricks (`\textcolor{white}`, `\phantom`), exfiltration image URLs
(`![](https://x/?q={chat})`) and `javascript:` links. Code blocks are correctly treated as visible.

### Unicode and emoji smuggling (all formats)
- **Unicode tag characters** (ASCII smuggling, U+E0000–E007F) are decoded; legitimate flags like 🏴󠁧󠁢󠁥󠁮󠁧󠁿 stay allowed.
- **Variation selector smuggling** (“text in emojis”): bytes attached to an emoji are decoded.
- **Zero-width steganography** (binary-encoded messages) and zero-width characters splitting words.
  Legitimate cases such as emoji ZWJ sequences or Persian ZWNJ are ignored.
- **Bidi overrides** (Trojan Source), control characters, ANSI escape codes (including `ESC[8m` conceal) and carriage-return overwriting.
- **Homoglyphs** (Cyrillic/Greek in Latin words) – replaced by the real letters when cleaning.
- **Styled letters:** 𝐛𝐨𝐥𝐝, ｆｕｌｌ-ｗｉｄｔｈ, 🅴🅼🅾🅹🅸 letters, regional indicator text, Zalgo.

### Encoded payloads
Base64, hex, `\x..`, `\u....`, URL encoding, HTML entities, binary, ROT13 and reversed text are decoded and checked against
the rule base again.

### Injection language (≈ 110 rules)
The rules cover instruction override, role hijacking and jailbreaks, system prompt extraction, fake chat markers
(`<|im_start|>`, `[INST]`, `<<SYS>>`), direct address to an AI (“Note to AI”, “Hinweis an die KI”), concealment
(“do not tell the user”), exfiltration, command execution and rating manipulation (e.g. “give a positive review” in CVs
and papers). All ten categories are covered in **English** (56 rules) and **German** (38 rules); for French, Spanish,
Italian, Portuguese and Dutch only the core “ignore all previous instructions” pattern is included. Language-independent
rules (chat markers, dangerous shell commands) apply to every text.

The rules run on a **normalised view** of the text: homoglyphs folded, accents removed, invisible characters ignored,
leetspeak (`1gn0r3`) and s p a c e d letters joined. An offset table maps every match back to the exact original position.
False positives are kept low by strict word boundaries (matches without spaces only inside provably obfuscated regions),
a negation filter (“never share your password”) and clustering: several weak signals together make a strong finding.

### Rating
Every finding has a score 0–100 (*Info* < 20 ≤ *Low* < 40 ≤ *Medium* < 65 ≤ *High* < 85 ≤ *Critical*). Hidden content
that also contains injection language is upgraded. The file risk is the strongest finding plus a damped share of further
*different* signals; repetitions of the same rule do not add up.

---

## Cleaning

| File type | Procedure |
|---|---|
| Text, Markdown, HTML | Selected ranges are removed character-exactly (whole sentences or elements). Homoglyphs and styled letters are replaced instead of deleted. Encoding (UTF-8/BOM, UTF-16, cp1252) and line endings are preserved. |
| PDF | Hidden text is removed from the content stream by redaction *without a visible box*. Annotations, links, metadata, JavaScript/launch actions and embedded files are removed. A `.cleaned.txt` with the clean text is exported as well. |
| Web pages | Exported as Markdown text in display order with detected tasks (see above). |

After cleaning, every file is scanned again and the report shows the risk before and after.

> Note for PDFs: if hidden text lies exactly *under* visible text, redaction removes both at that spot – the preview
> shows this immediately.

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The suite (190+ tests) covers attacks in English, German and 5 more languages, 11 obfuscation types, benign look-alikes, all smuggling techniques,
10 PDF hiding variants including rotated pages and OCR scans, cleaning with different encodings, website crawling against a
local test site, text/task extraction, English/German output, updates and the web API including token and DNS-rebinding
protection. `tools/make_samples.py` creates the demo files in `samples/` (`attack_*` / `benign_*`, German and English).

End-to-end test of the interface (drives Chrome through the DevTools protocol, no extra dependencies; needs Node ≥ 22 and Chrome):

```bash
python -m pif gui --no-browser --port 8812 &
node tests/ui_e2e.mjs http://127.0.0.1:8812/ "<path>/samples/attack_recipe.md,<path>/samples/attack_cv.pdf" "<export folder>"
```

The rule base was tuned against benign corpora (≈ 4,500 files from npm docs, the Python standard library, pip/numpy and
a 2,500-page HTML help site): 4 of 4,522 files (0.1 %) are rated *suspicious*, none *dangerous*.

## Platform tests

`.gitlab-ci.yml` starts the tool on every push exactly as a user does (`run_linux_mac.sh`) and then runs the full test
suite – on Debian 12, Ubuntu 24.04, Arch Linux and Fedora, with Python 3.9 and 3.13 – and tests the Linux installer.
Windows is tested locally (suite, start script, installer, EXE, browser E2E). macOS uses the same start script as Linux;
PyMuPDF and numpy ship ready-made packages for macOS (Intel and Apple Silicon), but there is no automatic macOS test.

## Standalone EXE (optional)

```bat
tools\build_exe.bat
```

Builds `dist\PromptInjectionFinder.exe` with PyInstaller; it runs without a Python installation.

## Security of the interface
The local server binds to `127.0.0.1` only. Every API request needs a random session token and the Host header is checked
(protection against DNS rebinding). A strict Content Security Policy prevents other websites in the browser from driving
the local API.

## Project structure
```
pif/
  patterns.py          rule base + matching engine
  normalize.py         normalised text views with offset mapping
  unicode_tools.py     character classes, smuggling decoders, homoglyphs
  text_analyzer.py     format-independent analysis
  markup_analyzer.py   Markdown/HTML hidden-content analysis
  css.py               colours, contrast, CSS hiding rules
  pdf_analyzer.py      PDF visibility analysis
  crawler.py, render.py  website crawling, optional JavaScript rendering
  textextract.py       readable text in display order + task detection
  scanner.py           file type detection, merging
  cleaner.py           cleaning + export
  report.py            HTML report
  i18n.py              English/German texts
  updater.py           update to the newest release
  server.py, web/      offline web interface
tests/                 pytest suite + browser E2E test
tools/                 sample generator, EXE build
samples/               demo files (attack_* / benign_*)
```

## License

Copyright (C) 2026 LuGG000

PromptInjectionFinder is free software: you can redistribute it and/or modify it under the terms of the
**GNU Affero General Public License v3.0 or later** (AGPL-3.0-or-later) as published by the Free Software Foundation –
see [LICENSE](LICENSE). It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Why AGPL: the PDF analysis uses [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (© Artifex, AGPL-3.0 or commercial
license), which the standalone EXE also bundles. Other third-party components: [NumPy](https://numpy.org) (BSD-3-Clause)
and, inside the EXE, the Python runtime (PSF License). If you distribute modified versions – including as a network
service – you must make your source code available under the same license.
