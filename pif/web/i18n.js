/* PromptInjectionFinder – UI texts in English and German. */
"use strict";

const I18N = {
  en: {
    brand_sub: "Offline · deterministic",
    choose_files: "Choose files", upload_folder: "Upload folder", scan_website: "Scan website", scan_path: "Scan path",
    clean_export: "Clean & export", check_updates: "Check for updates", toggle_theme: "Toggle light/dark",
    files: "Files", remove_all: "Remove all",
    drop_title: "Drop documents here", scan_by_link: "Scan a website by link",
    drop_text: "PDF, Markdown, text and HTML are checked locally for hidden prompt injections:<br>white/grey/tiny text, " +
      "covered text, invisible Unicode characters, emoji smuggling, homoglyphs, encoded payloads, hidden comments and more.",
    no_data_leaves: "No data leaves this computer.",
    tab_findings: "Findings", tab_document: "Document", tab_preview: "Cleaned preview",
    select_recommended: "Select recommended", select_all: "All", select_none: "None", download_cleaned: "Download cleaned",
    path_title: "Scan a local path", path_text: "File or folder on this computer (subfolders are included).",
    cancel: "Cancel", scan: "Scan", close: "Close",
    url_text: "Loads the page including its CSS, optionally follows links and sub-pages, and checks everything for hidden " +
      "prompt injections. This is the only feature that uses the internet.",
    url_address: "Address (URL)", url_depth: "Link depth", url_max: "Max. pages",
    depth0: "0 – this page only", depth1: "1 – plus directly linked pages", depth2: "2 – plus the pages linked from those",
    depth3: "3 – three levels deep",
    url_path: "Only pages below this address (e.g. …/wiki/…)", url_same: "Same domain only", url_docs: "Also scan linked documents (PDF, TXT, MD …)",
    url_discover: "Also try files mentioned in text/comments", url_robots: "Respect robots.txt",
    url_export_note: "Export for web pages: readable text in display order plus detected tasks as Markdown – no HTML.",
    render_with: (b) => `Run JavaScript – render the page like a browser (${b})`,
    render_none: "Run JavaScript – no Chrome/Edge/Chromium/Brave found, the static HTML is used",
    installed_version: "Installed version:",
    update_text: "The check asks the GitLab project for the newest release (the only internet access of this feature).",
    update_now: "Update now",
    export_text: "All files are cleaned with the findings selected for them and exported together with a report " +
      "(HTML + JSON). The originals stay unchanged.",
    export_only_findings: "Export only files with findings",
    zip_title: "Download as ZIP", zip_text: "Lands in the browser's download folder like any download.",
    zip_button: "Download ZIP", folder_title: "Save directly to a folder", target_folder: "Target folder",
    save_to_folder: "Save to folder",
    sev: { critical: "Critical", high: "High", medium: "Medium", low: "Low", info: "Info" },
    verdict: { dangerous: "Dangerous", suspicious: "Suspicious", clean: "Clean" },
    type: { pdf: "PDF", markdown: "Markdown", html: "HTML", text: "Text" },
    scanning: "Scanning…", scanning_n: (d, n) => `Scanning ${d} / ${n}…`, scanning_path: "Scanning path…",
    n_files_scanned: (n) => `${n} file(s) scanned`, error: "Error", read_error: "Could not be read",
    risk: "Risk", findings_n: (n) => `${n} finding${n === 1 ? "" : "s"}`,
    pages_n: (n) => `${n} page${n === 1 ? "" : "s"}`, chars_n: (n) => `${n} characters`, invisible_n: (n) => `${n} invisible`,
    web_rendered: "Web page · rendered with JavaScript", web_static: "Web page · static HTML",
    invisible_chars: (n) => `${n} invisible characters`, invisible_short: (n, f) => `${n}× invisible (${f}…)`,
    more_invisible: (n) => `+${n} more invisible`,
    loc_meta: "Metadata", loc_js: "Document actions", loc_attach: "Attachment", loc_page: (p) => `Page ${p}`,
    loc_line: (l) => `Line ${l}`, loc_source: "Page source",
    not_analysed: "The file could not be analysed: ", no_findings: "✔ Nothing suspicious found.",
    ocr_note: (p) => `Pages with an OCR text layer detected (${p}): invisible text over scans is normal there and is not ` +
      "counted as hidden.",
    grp_dangerous: "Dangerous", grp_suspicious: "Suspicious", grp_hints: "Hints",
    remove_on_clean: "Remove when cleaning", not_removable: "Cannot be removed automatically", remove_finding: "Remove finding",
    evidence: "Evidence", decoded: "Hidden / decoded content", show_in_doc: "Show in document",
    marks: "Highlights:", invisible_char: "= invisible character", preview_truncated: "· preview truncated",
    off_page: " (outside the page)", page: "Page",
    pdf_note: "Red frames mark text that humans cannot see (e.g. white on white, tiny, covered, outside the page). " +
      "Dashed = outside the visible area.",
    no_pages: "No pages", making_preview: "Creating cleaned preview…",
    removed_risk: (n, r, v) => `<b>${n}</b> finding(s) removed. Risk afterwards: <b>${r}/100</b> – ${v}.`,
    web_preview_note: "Web page: exported as <b>text in display order with detected tasks</b> (Markdown). Hidden content " +
      "is removed, collapsible parts are marked.",
    remaining: "Remaining: ",
    pdf_preview_note: "For PDFs the text of the cleaned PDF file is shown. Hidden text was removed by redaction (without " +
      "a visible box).",
    no_files_export: "No files to export", cleaning_zip: "Cleaning and packing ZIP…", cleaning_export: "Cleaning and exporting…",
    zip_done: (n) => `ZIP with ${n} cleaned file(s) and report downloaded.`,
    export_done: "Export finished: ", risk_short: "Risk", removed_n: (n) => `${n} removed`, open_folder: "Open folder",
    starting: "Starting…", phase_fetch: "Loading pages", phase_analyze: "Analysing", cancelled: "Cancelled. ",
    crawl_progress: (l, max, a) => `Loaded ${l}/${max} · analysed ${a}`, analysing_rest: (a, n) => `Analysing ${a}/${n}`,
    pages_scanned: (n) => `${n} page(s) scanned`, n_suspicious: (n) => ` – ${n} suspicious.`, all_clean: " – all clean.",
    log: "Log", cancelling: "Cancelling – finishing the page in progress …",
    group_web: "Website scan", group_folder: "Folder scan", group_upload: "Upload",
    files_count: (n) => `${n} file${n === 1 ? "" : "s"}`, n_flagged: (n) => `${n} flagged`, remove_scan: "Remove this scan",
    log_status: { loaded: "loaded", duplicate: "duplicate", skipped: "skipped", error: "error", http: "HTTP",
      limit: "limit", cancelled: "cancelled" },
    checking_update: "Checking for a new version …", new_version: (v) => `New version <b>${v}</b> available.`,
    exe_redownload: "<br>Please download the EXE version again.", newest: (v) => `You have the newest version (${v}).`,
    check_failed: "Check failed: ", updating: "Updating … (this can take a minute)",
    update_done: "Update installed. Please close the program (console window) and start it again.",
    update_failed: "Update failed: ", server_failed: "Connection to the local server failed: ",
  },
  de: {
    brand_sub: "Offline · deterministisch",
    choose_files: "Dateien wählen", upload_folder: "Ordner hochladen", scan_website: "Webseite scannen", scan_path: "Pfad scannen",
    clean_export: "Bereinigen & exportieren", check_updates: "Nach Updates suchen", toggle_theme: "Hell/Dunkel umschalten",
    files: "Dateien", remove_all: "Alle entfernen",
    drop_title: "Dokumente hier ablegen", scan_by_link: "Webseite per Link scannen",
    drop_text: "PDF, Markdown, Text und HTML werden lokal auf versteckte Prompt Injections geprüft:<br>weißer/grauer/winziger " +
      "Text, verdeckter Text, unsichtbare Unicode-Zeichen, Emoji-Smuggling, Homoglyphen, kodierte Payloads, versteckte " +
      "Kommentare und mehr.",
    no_data_leaves: "Keine Daten verlassen diesen Rechner.",
    tab_findings: "Funde", tab_document: "Dokument", tab_preview: "Bereinigte Vorschau",
    select_recommended: "Empfohlene wählen", select_all: "Alle", select_none: "Keine", download_cleaned: "Bereinigt herunterladen",
    path_title: "Lokalen Pfad scannen", path_text: "Datei oder Ordner auf diesem Rechner (Unterordner werden mitgescannt).",
    cancel: "Abbrechen", scan: "Scannen", close: "Schließen",
    url_text: "Lädt die Seite samt CSS, folgt optional Links und Unterseiten und prüft alles auf versteckte Prompt " +
      "Injections. Das ist die einzige Funktion, die das Internet nutzt.",
    url_address: "Adresse (URL)", url_depth: "Link-Tiefe", url_max: "Max. Seiten",
    depth0: "0 – nur diese Seite", depth1: "1 – plus direkt verlinkte Seiten", depth2: "2 – plus die dort verlinkten Seiten",
    depth3: "3 – drei Ebenen tief",
    url_path: "Nur Seiten unterhalb dieser Adresse (z. B. …/wiki/…)", url_same: "Nur dieselbe Domain", url_docs: "Verlinkte Dokumente mitscannen (PDF, TXT, MD …)",
    url_discover: "Auch im Text/in Kommentaren erwähnte Dateien ausprobieren", url_robots: "robots.txt beachten",
    url_export_note: "Export für Webseiten: lesbarer Text in Anzeige-Reihenfolge und erkannte Aufgaben als Markdown, kein HTML.",
    render_with: (b) => `JavaScript ausführen – Seite wie im Browser darstellen (${b})`,
    render_none: "JavaScript ausführen – kein Chrome/Edge/Chromium/Brave gefunden, es wird das statische HTML genutzt",
    installed_version: "Installierte Version:",
    update_text: "Die Prüfung fragt das GitLab-Projekt nach der neuesten Release-Version (einzige Internetverbindung " +
      "dieser Funktion).",
    update_now: "Jetzt aktualisieren",
    export_text: "Alle Dateien werden mit den jeweils ausgewählten Funden bereinigt und zusammen mit einem Bericht " +
      "(HTML + JSON) exportiert. Die Originale bleiben unverändert.",
    export_only_findings: "Nur Dateien mit Funden exportieren",
    zip_title: "Als ZIP herunterladen", zip_text: "Landet wie jeder Download im Download-Ordner des Browsers.",
    zip_button: "ZIP herunterladen", folder_title: "Direkt in einen Ordner speichern", target_folder: "Zielordner",
    save_to_folder: "In Ordner speichern",
    sev: { critical: "Kritisch", high: "Hoch", medium: "Mittel", low: "Niedrig", info: "Info" },
    verdict: { dangerous: "Gefährlich", suspicious: "Verdächtig", clean: "Unauffällig" },
    type: { pdf: "PDF", markdown: "Markdown", html: "HTML", text: "Text" },
    scanning: "Scanne…", scanning_n: (d, n) => `Scanne ${d} / ${n}…`, scanning_path: "Scanne Pfad…",
    n_files_scanned: (n) => `${n} Datei(en) gescannt`, error: "Fehler", read_error: "Fehler beim Lesen",
    risk: "Risiko", findings_n: (n) => `${n} Fund${n === 1 ? "" : "e"}`,
    pages_n: (n) => `${n} Seite${n === 1 ? "" : "n"}`, chars_n: (n) => `${n} Zeichen`, invisible_n: (n) => `${n} unsichtbar`,
    web_rendered: "Webseite · mit JavaScript dargestellt", web_static: "Webseite · statisches HTML",
    invisible_chars: (n) => `${n} unsichtbare Zeichen`, invisible_short: (n, f) => `${n}× unsichtbar (${f}…)`,
    more_invisible: (n) => `+${n} weitere unsichtbare`,
    loc_meta: "Metadaten", loc_js: "Dokument-Aktionen", loc_attach: "Anhang", loc_page: (p) => `Seite ${p}`,
    loc_line: (l) => `Zeile ${l}`, loc_source: "Seitenquelltext",
    not_analysed: "Die Datei konnte nicht analysiert werden: ", no_findings: "✔ Keine Auffälligkeiten gefunden.",
    ocr_note: (p) => `Seiten mit OCR-Textebene erkannt (${p}): unsichtbarer Text über Scans ist dort normal und wird ` +
      "nicht als versteckt gewertet.",
    grp_dangerous: "Gefährlich", grp_suspicious: "Verdächtig", grp_hints: "Hinweise",
    remove_on_clean: "Beim Bereinigen entfernen", not_removable: "Nicht automatisch entfernbar", remove_finding: "Fund entfernen",
    evidence: "Fundstelle", decoded: "Versteckter / dekodierter Inhalt", show_in_doc: "Im Dokument zeigen",
    marks: "Markierungen:", invisible_char: "= unsichtbares Zeichen", preview_truncated: "· Vorschau gekürzt",
    off_page: " (außerhalb der Seite)", page: "Seite",
    pdf_note: "Rote Rahmen markieren Text, den Menschen nicht sehen können (z. B. weiß auf weiß, winzig, verdeckt, " +
      "außerhalb der Seite). Gestrichelt = außerhalb des sichtbaren Bereichs.",
    no_pages: "Keine Seiten", making_preview: "Erzeuge bereinigte Vorschau…",
    removed_risk: (n, r, v) => `<b>${n}</b> Fund(e) entfernt. Risiko danach: <b>${r}/100</b> – ${v}.`,
    web_preview_note: "Webseite: Export als <b>Text in Anzeige-Reihenfolge mit erkannten Aufgaben</b> (Markdown). " +
      "Versteckte Inhalte sind entfernt, Aufklappbares ist markiert.",
    remaining: "Verbleibend: ",
    pdf_preview_note: "Für PDFs wird der Text der bereinigten PDF-Datei angezeigt. Versteckte Textstellen wurden per " +
      "Schwärzung (ohne sichtbare Box) entfernt.",
    no_files_export: "Keine Dateien zum Exportieren", cleaning_zip: "Bereinige und packe ZIP…",
    cleaning_export: "Bereinige und exportiere…",
    zip_done: (n) => `ZIP mit ${n} bereinigten Datei(en) und Bericht wurde heruntergeladen.`,
    export_done: "Export abgeschlossen: ", risk_short: "Risiko", removed_n: (n) => `${n} entfernt`, open_folder: "Ordner öffnen",
    starting: "Starte…", phase_fetch: "Lade Seiten", phase_analyze: "Analysiere", cancelled: "Abgebrochen. ",
    crawl_progress: (l, max, a) => `Geladen ${l}/${max} · analysiert ${a}`, analysing_rest: (a, n) => `Analysiere ${a}/${n}`,
    pages_scanned: (n) => `${n} Seite(n) gescannt`, n_suspicious: (n) => ` – ${n} auffällig.`, all_clean: " – alle unauffällig.",
    log: "Protokoll", cancelling: "Breche ab – die laufende Seite wird noch beendet …",
    group_web: "Website-Scan", group_folder: "Ordner-Scan", group_upload: "Upload",
    files_count: (n) => `${n} Datei${n === 1 ? "" : "en"}`, n_flagged: (n) => `${n} auffällig`, remove_scan: "Diesen Scan entfernen",
    log_status: { loaded: "geladen", duplicate: "Duplikat", skipped: "übersprungen", error: "Fehler", http: "HTTP",
      limit: "Limit", cancelled: "abgebrochen" },
    checking_update: "Prüfe auf neue Version …", new_version: (v) => `Neue Version <b>${v}</b> verfügbar.`,
    exe_redownload: "<br>Die EXE-Version bitte neu herunterladen.", newest: (v) => `Du hast die neueste Version (${v}).`,
    check_failed: "Prüfung fehlgeschlagen: ", updating: "Aktualisiere … (das kann eine Minute dauern)",
    update_done: "Update installiert. Bitte das Programm schließen (Konsolenfenster) und neu starten.",
    update_failed: "Update fehlgeschlagen: ", server_failed: "Verbindung zum lokalen Server fehlgeschlagen: ",
  },
};

let LANG = "en";
try { LANG = localStorage.getItem("pif-lang") || "en"; } catch (e) { /* storage blocked */ }
if (!I18N[LANG]) LANG = "en";

/** Translate a key; function entries receive the extra arguments. */
function t(key, ...args) {
  const v = I18N[LANG][key] ?? I18N.en[key] ?? key;
  return typeof v === "function" ? v(...args) : v;
}

/** Apply translations to static markup (data-i18n, data-i18n-html, data-i18n-title). */
function applyStaticI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  document.querySelectorAll("[data-i18n-html]").forEach((el) => (el.innerHTML = t(el.dataset.i18nHtml)));
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
    el.setAttribute("aria-label", el.title);
  });
  const b = document.getElementById("btn-lang");
  if (b) b.textContent = LANG === "de" ? "EN" : "DE";
}

function setLang(lang) {
  LANG = I18N[lang] ? lang : "en";
  try { localStorage.setItem("pif-lang", LANG); } catch (e) { /* ignore */ }
  applyStaticI18n();
}
