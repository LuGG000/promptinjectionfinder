"""Readable text of a web page in display order, plus detected exercises/tasks.

The HTML is walked in document order with the same CSS visibility logic the
scanner uses:
  * really hidden content (display:none without a way to show it, white text,
    off-screen, ...) is left out – that is where injections hide,
  * tabs / sub-pages that the user switches with a click are normal content,
  * content behind a click (solution, hint, <details>) is kept but marked as
    "aufklappbar",
  * form fields become "____", diagrams contribute their labels.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

from .css import background_of, hiding_reasons
from .markup_analyzer import (TAG_RE, VOID, _attrs, _css_rules, _element_props, _hidden_by_attrs,
                              toggle_reason)

BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "nav", "aside", "ul", "ol", "dl", "dt", "dd",
         "table", "thead", "tbody", "tfoot", "tr", "pre", "blockquote", "figure", "figcaption", "form", "fieldset",
         "legend", "details", "summary", "hr", "address", "center", "caption", "li", "h1", "h2", "h3", "h4", "h5",
         "h6", "br", "body", "html"}
SKIP = {"head", "script", "style", "template", "noscript", "button", "datalist", "title", "iframe", "object",
        "embed", "canvas", "audio", "video", "map", "math"}
TAB_HINT = re.compile(r"tab|page|panel|reiter|seite|sec|section|step|schritt|slide|kapitel|chapter", re.I)


@dataclass
class Block:
    kind: str            # h, p, li, tr, pre, fig, hr
    text: str = ""
    level: int = 0
    collapsed: bool = False
    marker: str = ""     # list marker
    tab: bool = False    # heading synthesised from a tab / sub-page name
    chrome: bool = False  # inside <nav>/<footer>/<aside>: page furniture, never part of a task


@dataclass
class Task:
    title: str
    context: list
    level: int = 0
    body: list = field(default_factory=list)       # Blocks
    extras: list = field(default_factory=list)     # titles of collapsed parts (Lösung, Tipp ...)
    signals: list = field(default_factory=list)


class _Out:
    def __init__(self):
        self.blocks = []
        self.cur = None
        self.boundary = False  # a block-ish element edge was crossed since the last text
        self.chrome = False

    def start(self, kind, collapsed, level=0, marker=""):
        self.flush()
        self.cur = Block(kind, "", level, collapsed, marker, chrome=self.chrome)

    def add(self, text, collapsed, pre=False):
        if not text:
            return
        if self.cur is None:
            self.cur = Block("p", "", 0, collapsed, chrome=self.chrome)
        if pre:
            self.cur.text += text
            return
        t = re.sub(r"\s+", " ", text)
        if self.cur.text.endswith((" ", "\n")) or not self.cur.text:
            t = t.lstrip()
        elif self.boundary and t[:1].isalnum() and self.cur.text[-1:].isalnum():
            t = " " + t
        if t.strip():
            self.boundary = False
        self.cur.text += t

    def flush(self):
        if self.cur is not None:
            txt = self.cur.text if self.cur.kind == "pre" else re.sub(r"[ \t]+\n", "\n", self.cur.text).strip()
            if txt or self.cur.kind == "hr":
                self.cur.text = txt
                self.blocks.append(self.cur)
        self.cur = None


def _labels_by_id(page: str) -> dict:
    out = {}
    for m in re.finditer(r"<([a-zA-Z][\w-]*)\b[^>]*\bid\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</\1\s*>", page, re.S):
        txt = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", m.group(3)))).strip()
        if txt and len(txt) <= 80:
            out.setdefault(m.group(2), txt)
    return out


def extract_blocks(page: str, extra_css: str = "") -> list:
    page = re.sub(r"<![^-][^>]*>|<\?[^>]*\?>", "", page)  # doctype / processing instructions
    css, toggles = _css_rules(page, extra_css)
    labels = None
    scripts = " ".join(m.group(1) for m in re.finditer(r"<script\b[^>]*>(.*?)</script\s*>", page, re.S | re.I))
    out = _Out()
    stack = []  # dicts: tag, hidden, collapsed, skip, info, bg, list_counter
    pos = 0
    n = len(page)
    svg_text = None

    def state():
        hidden = any(e["hidden"] for e in stack)
        collapsed = any(e["collapsed"] for e in stack)
        skip = any(e["skip"] for e in stack)
        pre = any(e["tag"] == "pre" for e in stack)
        return hidden, collapsed, skip, pre

    def text_between(a, b):
        nonlocal svg_text
        if a >= b:
            return
        hidden, collapsed, skip, pre = state()
        if hidden or skip:
            return
        t = _html.unescape(page[a:b])
        if svg_text is not None:
            if t.strip():
                svg_text.append(t.strip())
            return
        out.add(t, collapsed, pre)

    while pos < n:
        m = TAG_RE.search(page, pos)
        if not m:
            text_between(pos, n)
            break
        text_between(pos, m.start())
        pos = m.end()
        tok = m.group(0)
        if tok.startswith("<!--"):
            continue
        closing, tag, rawattrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        hidden, collapsed, skip, _pre = state()
        if closing:
            idx = next((k for k in range(len(stack) - 1, -1, -1) if stack[k]["tag"] == tag), None)
            if idx is None:
                continue
            while len(stack) > idx:
                el = stack.pop()
                if el["tag"] == "svg" and svg_text is not None and el is el.get("svg_owner"):
                    words = []
                    for w in svg_text:
                        if w not in words:
                            words.append(w)
                    svg_text = None
                    h2, c2, s2, _ = state()
                    if words and not h2 and not s2:
                        out.start("fig", c2)
                        out.add("[Grafik: " + " · ".join(words) + "]", c2)
                        out.flush()
                if el["tag"] in BLOCK:
                    out.flush()
                out.chrome = any(e["tag"] in ("nav", "footer", "aside") or e.get("role") in ("navigation", "contentinfo")
                                 for e in stack)
                if el.get("boundary"):
                    out.boundary = True
                if el["tag"] == "summary" and stack and stack[-1]["tag"] == "details" and stack[-1].get("closed_details"):
                    stack[-1]["collapsed"] = True  # content after <summary> is behind a click
            continue

        attrs = _attrs(rawattrs)
        if tag in ("textarea", "title", "script", "style"):
            endm = re.compile(r"</" + tag + r"\s*>", re.I).search(page, pos)
            if tag == "textarea" and not (hidden or skip):
                out.add(" ____ ", collapsed)
            pos = endm.end() if endm else n
            continue
        props = _element_props(tag, attrs, css, [e["info"] for e in stack])
        parent_bg = next((e["bg"] for e in reversed(stack) if e["bg"] is not None), None)
        bg = background_of(props) or parent_bg
        hard, soft = hiding_reasons(props, bg if bg is not None else (255, 255, 255))
        h2, _s2 = _hidden_by_attrs(tag, attrs)
        hard += h2
        tog = toggle_reason(hard, attrs, toggles, scripts)
        el_hidden = bool(hard) and not tog
        classes = set(attrs.get("class", "").lower().split())
        ident = attrs.get("class", "") + " " + attrs.get("id", "")
        # a tab / sub-page container – whether it is the visible one or not
        is_tab = (attrs.get("role", "").lower() == "tabpanel"
                  or (bool(tog or classes & toggles) and TAB_HINT.search(ident) is not None)
                  ) and not re.search(r"sol|loes|lös|hint|tipp|answer|antwort", ident, re.I)
        el_collapsed = bool(tog) and not is_tab

        # void / inline replacements
        if tag in VOID or selfclose:
            if hidden or skip or el_hidden:
                continue
            if tag == "br":
                out.add("\n", collapsed, pre=True)
            elif tag == "hr":
                out.start("hr", collapsed)
                out.flush()
            elif tag == "input":
                typ = attrs.get("type", "text").lower()
                if typ in ("checkbox", "radio"):
                    out.add(" ☐ ", collapsed)
                elif typ not in ("hidden", "submit", "button", "reset", "image", "file", "range", "color"):
                    out.add(f" {attrs['value']} " if attrs.get("value") else " ____ ", collapsed)
            elif tag == "img" and attrs.get("alt", "").strip():
                out.add(f" [Bild: {attrs['alt'].strip()}] ", collapsed)
            continue

        entry = {"tag": tag, "hidden": el_hidden, "collapsed": el_collapsed, "skip": tag in SKIP,
                 "role": attrs.get("role", "").lower(),
                 "info": {"tag": tag, "classes": frozenset(attrs.get("class", "").lower().split()),
                          "ids": frozenset([attrs["id"].lower()] if attrs.get("id") else [])},
                 "bg": background_of(props)}
        if tag == "details" and "open" not in attrs:
            entry["closed_details"] = True
        disp = (props.get("display") or "").split()[0] if props.get("display") else ""
        entry["display"] = disp
        parent_flex = bool(stack) and stack[-1].get("display") in ("flex", "inline-flex", "grid", "inline-grid")
        if tag not in ("sub", "sup") and (parent_flex or disp in ("block", "inline-block", "flex", "inline-flex", "grid",
                                                                   "inline-grid", "table-cell", "list-item")
                                          or tag in ("td", "th")):
            out.boundary = True
            entry["boundary"] = True
        stack.append(entry)
        out.chrome = any(e["tag"] in ("nav", "footer", "aside") or e.get("role") in ("navigation", "contentinfo")
                         for e in stack)
        if tag == "svg" and svg_text is None:
            svg_text = []
            entry["svg_owner"] = entry
        hidden, collapsed, skip, _pre = state()
        if hidden or skip:
            continue
        if is_tab:
            if labels is None:
                labels = _labels_by_id(page)
            name = (labels.get(attrs.get("aria-labelledby", "")) or attrs.get("data-nav") or attrs.get("data-title")
                    or attrs.get("aria-label") or attrs.get("title") or "")
            name = re.sub(r"\s*\(?\d+\s*/\s*\d+\)?\s*$", "", name)  # progress counters like "0/4"
            if name:
                out.start("h", collapsed, level=2)
                out.add(name, collapsed)
                out.cur.tab = True
                out.flush()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            out.start("h", collapsed, level=int(tag[1]))
        elif tag == "li":
            lists = [e for e in stack[:-1] if e["tag"] in ("ul", "ol")]
            marker = "-"
            if lists and lists[-1]["tag"] == "ol":
                lists[-1]["n"] = lists[-1].get("n", 0) + 1
                marker = f"{lists[-1]['n']}."
            out.start("li", collapsed, level=max(1, len(lists)), marker=marker)
        elif tag == "tr":
            out.start("tr", collapsed)
        elif tag in ("td", "th"):
            if out.cur is not None and out.cur.kind == "tr" and out.cur.text:
                out.add(" | ", collapsed, pre=True)
        elif tag == "pre":
            out.start("pre", collapsed)
        elif tag == "select":
            opts = re.findall(r"<option\b[^>]*>(.*?)</option>", page[pos:pos + 5000], re.S | re.I)
            out.add(" [Auswahl: " + " / ".join(_html.unescape(re.sub(r"<[^>]+>", "", o)).strip() for o in opts[:8]) + "] ",
                    collapsed)
            endm = re.compile(r"</select\s*>", re.I).search(page, pos)
            pos = endm.end() if endm else n
            stack.pop()
        elif tag in BLOCK:
            out.start("p", collapsed)
    out.flush()
    return out.blocks


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

_TASK_TITLE = re.compile(r"\b(aufgaben?|teilaufgaben?|übung(en)?|uebung(en)?|arbeitsauftr(ag|äge)|auftrag|tasks?|"
                         r"exercises?|fragen?|kontrollfragen|quiz|test|lernkontrolle|selbstkontrolle|selbsttest|"
                         r"wiederholungsfragen|challenge|problem|mission|questions?)\b|^\s*(\d+[.)]|[a-h]\))\s", re.I)
_OPERATORS = (
    r"berechne|bestimme|ermittle|erkläre|erläutere|beschreibe|nenne|gib|zeichne|skizziere|begründe|vergleiche|"
    r"analysiere|beurteile|bewerte|entwickle|entwirf|stelle|überprüfe|prüfe|löse|ergänze|vervollständige|ordne|"
    r"recherchiere|notiere|formuliere|wandle|rechne|miss|messe|schreibe|erstelle|implementiere|programmiere|"
    r"konfiguriere|installiere|schließe|teste|dokumentiere|diskutiere|interpretiere|überlege|untersuche|simuliere|"
    r"baue|trage|kreuze|markiere|fülle|dimensioniere|wähle|zeige|leite|kennzeichne|benenne|definiere|fasse|"
    r"übersetze|vereinfache|forme|stelle|überführe|"
    r"beschreibt|berechnet|bestimmt|ermittelt|erklärt|erläutert|nennt|zeichnet|skizziert|begründet|vergleicht|"
    r"analysiert|bewertet|entwickelt|entwerft|erstellt|notiert|formuliert|recherchiert|überlegt|diskutiert|"
    r"präsentiert|plant|baut|testet|dokumentiert|legt|sucht|sammelt|ordnet|ergänzt|löst|prüft|untersucht|"
    r"gestaltet|programmiert|implementiert|"
    r"berechnen|bestimmen|ermitteln|erklären|erläutern|beschreiben|nennen|geben|zeichnen|begründen|vergleichen|"
    r"calculate|determine|explain|describe|name|list|draw|compare|solve|write|create|implement|find|identify|"
    r"justify|evaluate|complete|fill"
)
_OPERATOR_START = re.compile(r"(?:^|[.!?:]\s+|\n)\s*(?:\(?\d+[.)]\s*|\(?[a-h]\)\s*|[-•]\s*)?(" + _OPERATORS + r")\b"
                             r"(?:\s+sie\b)?", re.I)
_EXTRA_TITLES = re.compile(r"lösung|loesung|lösungsweg|tipp|hinweis|hilfe|solution|answer|hint|antwort", re.I)


_TASK_LABEL = re.compile(r"^(aufgabe|teilaufgabe|übung|uebung|task|exercise|frage|nr\.?)\s*[\d.]+[a-z]?\s*:?$", re.I)
_UI_NOISE = re.compile(r"^(offen|gelöst|erledigt|richtig|falsch|neu|open|done|solved|todo|\d+ von \d+ .*gelöst)$", re.I)


def _extra_label(block) -> str:
    t = block.text.strip()
    m = re.match(r"([^:\n]{2,20}):", t)
    if m:
        return m.group(1).strip()
    return " ".join(t.split()[:3]) + ("…" if len(t.split()) > 3 else "")


def detect_tasks(blocks: list) -> list:
    tasks = []
    path = []  # [(level, title)]
    cur = None
    top_level = min((b.level for b in blocks if b.kind == "h" and not b.tab), default=1)

    def finish():
        if cur is None:
            return
        body_text = "\n".join(b.text for b in cur.body if not b.collapsed)
        sig = []
        if _TASK_TITLE.search(cur.title):
            sig.append("Überschrift")
        if ("____" in body_text or "☐" in body_text
                or any(b.kind == "tr" and re.search(r"\|\s*(\||$)", b.text) for b in cur.body if not b.collapsed)):
            sig.append("Eingabefelder")  # form fields or table cells left empty to be filled in
        if _OPERATOR_START.search(body_text) or _OPERATOR_START.search(cur.title):
            sig.append("Arbeitsanweisung")
        questions = len(re.findall(r"\?\s*(?:\n|$)", body_text))
        if questions >= 2:
            sig.append("Fragen")
        elif questions:
            sig.append("Frage")
        if any(_EXTRA_TITLES.search(x) for x in cur.extras):
            sig.append("Lösung/Tipp")
        weight = sum({"Überschrift": 2, "Eingabefelder": 2, "Arbeitsanweisung": 1, "Frage": 1, "Fragen": 2,
                      "Lösung/Tipp": 1}[s] for s in sig)
        if cur.level <= top_level and "Eingabefelder" not in sig:
            weight = 0  # page title / chapter intro, not an exercise
        if weight >= 2 and body_text.strip():
            cur.signals = sig
            tasks.append(cur)

    for b in blocks:
        if b.chrome or (b.kind in ("p", "li") and _UI_NOISE.match(b.text.strip())):
            continue
        if b.kind == "h" and not b.collapsed:
            label = ""
            if cur is not None and cur.body and _TASK_LABEL.match(cur.body[-1].text.strip()):
                label = cur.body.pop().text.strip().rstrip(":")
            finish()
            while path and path[-1][0] >= b.level:
                path.pop()
            cur = Task(f"{label}: {b.text}" if label else b.text, [t for _, t in path])
            cur.level = b.level
            path.append((b.level, b.text))
        elif cur is None:
            cur = Task("", [])
            cur.level = 0
            if b.collapsed:
                continue
            cur.body.append(b)
        elif b.collapsed:
            if b.kind == "h":
                cur.extras.append(b.text)
            elif not (cur.body and cur.body[-1].collapsed):
                prev = cur.body[-1] if cur.body else None
                # the visible trigger (e.g. <summary>Hinweis</summary>) names the hidden part best
                cur.extras.append(prev.text if prev is not None and len(prev.text) <= 25 else _extra_label(b))
            cur.body.append(b)
        else:
            cur.body.append(b)
    finish()

    # Pages without headings: single paragraphs with work instructions
    if not tasks:
        for b in blocks:
            if b.kind in ("p", "li") and not b.collapsed and _OPERATOR_START.search(b.text) and len(b.text) > 25:
                t = Task("", [], body=[b])
                t.signals = ["Arbeitsanweisung"]
                tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def blocks_to_markdown(blocks: list, heading_offset: int = 1) -> str:
    lines = []
    prev_collapsed = False
    prev_kind = None
    for b in blocks:
        if b.collapsed and not prev_collapsed:
            lines.append("")
            lines.append("> ▸ *aufklappbar (erst nach Klick sichtbar)*")
        if not b.collapsed and prev_collapsed:
            lines.append("")
        q = "> " if b.collapsed else ""
        if b.kind == "h":
            lines.append(q.rstrip() if q else "")
            lines.append(q + "#" * min(6, b.level + heading_offset) + " " + b.text)
        elif b.kind == "li":
            lines.append(q + "  " * (b.level - 1) + f"{b.marker} " + b.text.replace("\n", " "))
        elif b.kind == "tr":
            lines.append(q + "| " + b.text.replace("\n", " ") + " |")
        elif b.kind == "pre":
            lines.append(q + "```")
            lines.extend(q + ln for ln in b.text.rstrip("\n").split("\n"))
            lines.append(q + "```")
        elif b.kind == "hr":
            lines.append(q + "---")
        elif b.kind == "fig":
            lines.append(q + "*" + b.text + "*")
        else:
            if prev_kind in ("p", "fig", "pre", "tr", "li") or prev_kind == "h":
                lines.append(q.rstrip() if q else "")
            lines.extend(q + ln for ln in b.text.split("\n"))
        prev_collapsed = b.collapsed
        prev_kind = b.kind
    md = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


def tasks_to_markdown(tasks: list, heading: str = "##") -> str:
    if not tasks:
        return f"{heading} Erkannte Aufgaben\n\n*Keine Aufgaben erkannt.*\n"
    parts = [f"{heading} Erkannte Aufgaben ({len(tasks)})\n"]
    for i, t in enumerate(tasks, 1):
        title = t.title or "Aufgabe"
        parts.append(f"{heading}# {i}. {title}")
        meta = []
        if t.context:
            meta.append("Abschnitt: " + " › ".join(t.context))
        meta.append("erkannt an: " + ", ".join(t.signals))
        parts.append("*" + " · ".join(meta) + "*\n")
        parts.append(blocks_to_markdown(t.body, heading_offset=3).strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def page_title(page: str, blocks: list) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    if m and m.group(1).strip():
        return re.sub(r"\s+", " ", _html.unescape(m.group(1))).strip()
    h = next((b.text for b in blocks if b.kind == "h"), "")
    return h or "Webseite"


def web_markdown(page: str, url: str = "", extra_css: str = "", note: str = "") -> tuple:
    """Return (markdown, tasks) for one HTML page."""
    blocks = extract_blocks(page, extra_css)
    tasks = detect_tasks(blocks)
    title = page_title(page, blocks)
    head = [f"# {title}", ""]
    if url:
        head.append(f"Quelle: <{url}>  ")
    if note:
        head.append(note + "  ")
    head.append("")
    md = "\n".join(head) + "\n" + tasks_to_markdown(tasks) + "\n---\n\n## Seitentext (in Anzeige-Reihenfolge)\n\n" + \
        blocks_to_markdown(blocks, heading_offset=2)
    return md, tasks
