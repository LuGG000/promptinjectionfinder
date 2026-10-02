"""Entry point: scan a file (bytes) and return a ScanResult."""
from __future__ import annotations

import codecs
import os
import re

from .i18n import T, text as i18n_text, tr
from .markup_analyzer import analyze_markup, code_text, strip_tags
from .models import ScanResult
from .text_analyzer import analyze_text

TEXT_EXT = {".txt", ".text", ".log", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml", ".yml", ".ini", ".cfg",
            ".rst", ".tex", ".srt", ".vtt", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".sh",
            ".ps1", ".bat", ".sql", ".toml", ".eml"}
MD_EXT = {".md", ".markdown", ".mdown", ".mkd", ".mdx"}
HTML_EXT = {".html", ".htm", ".xhtml", ".svg"}
PDF_EXT = {".pdf"}
SUPPORTED_EXT = TEXT_EXT | MD_EXT | HTML_EXT | PDF_EXT

PREVIEW_LIMIT = 400_000


def detect_type(name: str, data: bytes) -> str:
    ext = os.path.splitext(name)[1].lower()
    if data[:5] == b"%PDF-" or (ext in PDF_EXT and b"%PDF-" in data[:1024]):
        return "pdf"
    if ext in MD_EXT:
        return "markdown"
    if ext in HTML_EXT:
        return "html"
    if ext in TEXT_EXT:
        return "text"
    head = data[:2048].lower()
    if b"<html" in head or b"<!doctype html" in head:
        return "html"
    return "text"


def decode_text(data: bytes) -> tuple:
    """Return (text, encoding). Detects BOMs and UTF-16 without BOM."""
    for bom, enc in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                     (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if data.startswith(bom):
            return data.decode(enc, errors="replace"), enc
    if len(data) >= 4 and data[1:2] == b"\x00" and data[3:4] == b"\x00" and data[0:1] != b"\x00":
        try:
            return data.decode("utf-16-le"), "utf-16-le"
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def absorb_into_hidden(findings: list, hosts=None) -> list:
    """Drop injection findings whose every rule match lies inside a hidden region
    and raise the score of the hidden region instead."""
    hosts = hosts if hosts is not None else [
        f for f in findings if f.category in ("hidden", "unicode", "encoding") and f.location.start is not None
        and f.location.end is not None and not f.location.ranges]
    out = []
    for f in findings:
        if f.category == "injection" and f.location.start is not None:
            spans = f.hit_spans or [[f.location.start, f.location.end]]
            owners = []
            for s, e in spans:
                h = next((h for h in hosts if h.location.start <= s and e <= h.location.end + 2), None)
                if h is None:
                    owners = None
                    break
                owners.append(h)
            if owners:
                for host in set(map(id, owners)):
                    h = next(o for o in owners if id(o) == host)
                    h.score = max(h.score, min(100.0, f.score + 20))
                    if "injection" not in h.tags:
                        h.tags.append("injection")
                    h.default_remove = True
                    if str(f.title) not in str(h.description):
                        h.description = tr(h.description) + T(" Detected: ", " Erkannt: ") + f.title + "."
                continue
        out.append(f)
    return out


def _absorb(findings: list) -> list:
    """Injection phrases inside hidden regions are folded into the hidden finding
    (one actionable finding instead of two overlapping ones)."""
    out = absorb_into_hidden(findings)
    # de-duplicate identical rule + range
    seen = set()
    final = []
    for f in out:
        key = (f.rule, f.location.start, f.location.end, f.location.page, f.location.target)
        if key in seen:
            continue
        seen.add(key)
        final.append(f)
    return final


def _commands_in_code(findings: list, text: str, is_html: bool) -> None:
    """Install/how-to pages show commands like "curl … | sh" in code blocks for the reader to copy.
    A pure command finding whose matches all lie in visible code is information, not an attack
    (hidden code blocks are reported by the hidden-content checks)."""
    code = None
    for f in findings:
        if f.category != "injection" or f.tags != ["tool"] or not f.hit_spans:
            continue
        if code is None:
            code = code_text(text, is_html)
        if code and all(re.sub(r"\s+", "", text[s:e]).lower() in code for s, e in f.hit_spans):
            f.score = min(f.score, 15.0)
            f.default_remove = False
            f.description = tr(f.description) + T(
                " (Shown in a code block – usual for installation and how-to instructions, so not counted as an attack.)",
                " (Steht in einem Code-Block – üblich für Installations- und Anleitungsseiten, daher nicht als Angriff "
                "gewertet.)")


def scan_bytes(name: str, data: bytes, path: str = "", extra_css: str = "") -> ScanResult:
    """``extra_css``: external stylesheets of a web page (needed to see CSS-hidden text)."""
    ftype = detect_type(name, data)
    result = ScanResult(path=path or name, name=os.path.basename(name), filetype=ftype)
    try:
        if ftype == "pdf":
            from .pdf_analyzer import analyze_pdf
            findings, text, stats = analyze_pdf(data)
            result.findings = findings
            result.text_preview = text[:PREVIEW_LIMIT]
            result.stats = stats
        else:
            text, enc = decode_text(data)
            findings = analyze_text(text)
            if ftype in ("markdown", "html"):
                findings += analyze_markup(text, is_html=ftype == "html", extra_css=extra_css)
            result.findings = _absorb(findings)
            if ftype in ("markdown", "html"):
                _commands_in_code(result.findings, text, ftype == "html")
            result.text_preview = text[:PREVIEW_LIMIT]
            result.stats = {"encoding": enc, "chars": len(text), "lines": text.count("\n") + 1,
                            "truncated_preview": len(text) > PREVIEW_LIMIT}
    except Exception as exc:  # report, never crash the whole batch
        result.error = f"{type(exc).__name__}: {exc}"
    result.findings.sort(key=lambda f: -f.score)
    return result


def _same_finding_key(f) -> tuple:
    """Identity of a finding across the rendered DOM and the delivered source: the matched words for
    pattern findings, else the text without markup (the HTML around it differs between the two)."""
    m = re.search(r"Matches: (.+)$", i18n_text(f.description, "en"))
    if f.category == "injection" and m:
        return f.rule, m.group(1)
    return f.rule, " ".join(strip_tags(f.decoded or f.evidence).split())[:200]


def scan_web_page(name: str, data: bytes, url: str, extra_css: str = "", source: bytes = b"") -> ScanResult:
    """Scan a crawled HTML page. ``data`` is the rendered DOM (or the HTML), ``source`` the
    delivered HTML when the page was rendered: findings that exist only in the source code
    (e.g. removed by JavaScript, but still read by scrapers/LLM tools) are added for information."""
    res = scan_bytes(name, data, path=url, extra_css=extra_css)
    res.stats["web"] = True
    res.stats["url"] = url
    res.stats["rendered"] = bool(source)
    if source:
        src = scan_bytes(name, source, path=url, extra_css=extra_css)
        seen = {_same_finding_key(f) for f in res.findings}
        for f in src.findings:
            if _same_finding_key(f) in seen or f.score < 20:
                continue
            f.title = T("Only in page source: ", "Nur im Seitenquelltext: ") + f.title
            f.description = tr(f.description) + T(
                " (Present in the delivered source code but not in the displayed page – scrapers and AI tools still read it.)",
                " (Im Quelltext vorhanden, in der dargestellten Seite nicht – Scraper und KI-Tools lesen ihn trotzdem.)")
            f.location.start = f.location.end = None
            f.location.ranges = []
            f.location.target = "source"
            f.removable = False
            f.default_remove = False
            res.findings.append(f)
        res.findings.sort(key=lambda f: -f.score)
    return res


def scan_file(path: str) -> ScanResult:
    with open(path, "rb") as fh:
        data = fh.read()
    return scan_bytes(os.path.basename(path), data, path=path)


def iter_files(paths, recursive: bool = True):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
                for fn in sorted(files):
                    if os.path.splitext(fn)[1].lower() in SUPPORTED_EXT:
                        yield os.path.join(root, fn)
                if not recursive:
                    break
        elif os.path.isfile(p):
            yield p
