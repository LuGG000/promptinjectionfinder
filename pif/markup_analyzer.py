"""Hidden-content analysis for Markdown and HTML.

Finds content that a renderer hides from humans but that an LLM still reads:
comments, CSS-hidden or near-invisible elements (white/grey/tiny/off-screen),
LaTeX colour tricks, alt texts, front matter, and markdown image exfiltration.
"""
from __future__ import annotations

import html
import re

from .css import UNKNOWN_BG, background_of, hiding_reasons, parse_color, parse_style, resolve_vars
from .models import Finding, Location
from .patterns import payload_score
from .text_analyzer import _payload_note, context, line_of, visible_repr

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
RAW_TEXT = {"script", "style", "textarea", "title"}
HIDDEN_CLASSES = {"sr-only", "visually-hidden", "screen-reader-text", "d-none", "hidden", "invisible", "hide",
                  "visuallyhidden", "screenreader", "offscreen", "is-hidden", "u-hidden"}

TAG_RE = re.compile(
    r"<!--.*?(?:-->|$)|<(/?)([a-zA-Z][a-zA-Z0-9:-]*)((?:\s+[^\s/>=\"']+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>\"']+))?)*)\s*(/?)>",
    re.S)
ATTR_RE = re.compile(r"([^\s/>=\"']+)(?:\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>\"']+))?")
CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def strip_tags(s: str) -> str:
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()


def _hidden_finding(text, s, e, inner, rule, title, why, base=30.0, soft=False):
    ps, hits = payload_score(inner)
    words = len(inner.split())
    if hits:
        score = min(100.0, max(60.0, ps + 25)) if not soft else min(100.0, max(55.0, ps + 18))
    elif words >= 3:
        score = base if not soft else min(base, 22.0)
    elif words >= 1:
        score = 12.0
    else:
        return None
    return Finding(
        category="hidden",
        rule=rule,
        title=title,
        description=why + _payload_note(hits),
        score=score,
        evidence=visible_repr(text[s:e][:500]),
        decoded=inner[:3000],
        location=Location(start=s, end=e, line=line_of(text, s)),
        default_remove=bool(hits) or (not soft and words >= 3 and base >= 20),
        tags=["hidden"] + (["injection"] if hits else []),
    )


def _attrs(raw: str) -> dict:
    out = {}
    for m in ATTR_RE.finditer(raw or ""):
        v = m.group(2)
        if v and v[0] in "\"'":
            v = v[1:-1]
        out[m.group(1).lower()] = html.unescape(v) if v is not None else ""
    return out


def _compound(sel: str):
    """Parse 'div.a.b#x' into (tag, classes, ids); None for unsupported parts."""
    if re.search(r":{1,2}(before|after|hover|focus|active|visited|placeholder|selection)", sel):
        return None  # pseudo elements/states do not describe the static text
    sel = re.sub(r":{1,2}[\w-]+(\([^)]*\))?", "", sel)
    if not sel or "[" in sel or "*" in sel:
        return None
    tag = None
    classes, ids = set(), set()
    for prefix, name in re.findall(r"([.#]?)([\w-]+)", sel):
        if prefix == ".":
            classes.add(name)
        elif prefix == "#":
            ids.add(name)
        else:
            tag = name
    return (tag, frozenset(classes), frozenset(ids))


def _media_applies(query: str) -> bool:
    """Assume a desktop screen: skip print and small-screen media blocks."""
    q = query.lower()
    if re.search(r"\bprint\b|\bspeech\b", q) and "screen" not in q:
        return False
    if re.search(r"max-(device-)?width|orientation\s*:\s*portrait|hover\s*:\s*none|pointer\s*:\s*coarse", q):
        return False
    return True


def _css_blocks(css: str):
    """Yield (selector_text, body) for every style rule that applies on screen.

    Handles nested at-rules (@media, @supports, @layer, @container) and skips
    @keyframes, @font-face, @page and print/mobile-only media blocks."""
    i, n = 0, len(css)
    while i < n:
        brace = css.find("{", i)
        if brace < 0:
            return
        close_ = css.find("}", i)
        if 0 <= close_ < brace:  # stray closing brace
            i = close_ + 1
            continue
        prelude = css[i:brace].strip()
        # find the matching closing brace
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        body = css[brace + 1:j - 1]
        if prelude.startswith("@"):
            name = prelude[1:].split(None, 1)[0].lower() if len(prelude) > 1 else ""
            if name == "media":
                if _media_applies(prelude[6:]):
                    yield from _css_blocks(body)
            elif name in ("supports", "layer", "container", "document", "scope"):
                yield from _css_blocks(body)
        elif prelude:
            yield prelude, body
        i = j


_SHOWS = re.compile(r"display\s*:\s*(?!none)[a-z-]+|visibility\s*:\s*visible|opacity\s*:\s*(1|0?\.[5-9])|max-height\s*:\s*(?!0)")


def _css_rules(text: str, extra_css: str = "") -> tuple:
    """Return ([(specificity, order, compounds, props)], toggle_classes).

    ``compounds`` lists the descendant chain, the last one being the element.
    ``toggle_classes`` are classes that are hidden by default but have a rule
    that shows them in some state (.page.active, .tab:target, .open .panel …):
    tabs, accordions and sub-pages that a user reaches by clicking."""
    sheets = [extra_css or ""]
    sheets += [b.group(1) for b in re.finditer(r"<style\b[^>]*>(.*?)</style\s*>", text, re.S | re.I)]
    rules = []
    raw_rules = []
    order = 0
    for css in sheets:
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for selector_text, body in _css_blocks(css):
            props = parse_style(body)
            for sel in selector_text.split(","):
                sel = sel.strip().lower()
                if not sel:
                    continue
                raw_rules.append((sel, body.lower()))
                chain = [_compound(p) for p in re.split(r"\s*[>+~]\s*|\s+", sel) if p]
                if not chain or any(c is None for c in chain):
                    continue
                spec = sum(len(c[2]) * 100 + len(c[1]) * 10 + (1 if c[0] else 0) for c in chain)
                order += 1
                rules.append((spec, order, chain, props))
    rules.sort(key=lambda r: (r[0], r[1]))
    variables = {}
    for _sel, body in raw_rules:  # custom properties live in :root, html, body, …
        for k, v in parse_style(body).items():
            if k.startswith("--"):
                variables[k] = v
    rules = [(sp, o, ch, resolve_vars(pr, variables)) for sp, o, ch, pr in rules]
    _css_rules.variables = variables
    toggles = set()
    for sel, body in raw_rules:
        if not _SHOWS.search(body):
            continue
        for cls in re.findall(r"\.([\w-]+)", sel):
            if re.fullmatch(r"(?:[a-z0-9]*)\." + re.escape(cls), sel):
                continue  # the plain rule itself is not a state
            toggles.add(cls)
    return rules, toggles


def _matches(compound, info) -> bool:
    tag, classes, ids = compound
    return ((tag is None or tag == info["tag"]) and classes <= info["classes"] and ids <= info["ids"])


def _element_props(tag: str, attrs: dict, css: list, ancestors=()) -> dict:
    props = {}
    me = {"tag": tag, "classes": frozenset(attrs.get("class", "").lower().split()),
          "ids": frozenset([attrs["id"].lower()] if attrs.get("id") else [])}
    for _spec, _order, chain, rprops in css:
        if not _matches(chain[-1], me):
            continue
        # descendant semantics: earlier compounds must match ancestors in order
        k = len(chain) - 2
        for anc in reversed(ancestors):
            if k < 0:
                break
            if _matches(chain[k], anc):
                k -= 1
        if k < 0:
            props.update(rprops)
    if tag == "font" and attrs.get("color"):
        props["color"] = attrs["color"].lower()
    if attrs.get("bgcolor"):
        props["background-color"] = attrs["bgcolor"].lower()
    props.update(parse_style(attrs.get("style", "")))
    variables = getattr(_css_rules, "variables", {})
    return resolve_vars(props, variables) if variables else props


def _hidden_by_attrs(tag: str, attrs: dict) -> tuple:
    hard, soft = [], []
    if "hidden" in attrs:
        hard.append("hidden-Attribut")
    if tag == "template":
        hard.append("<template> wird nicht dargestellt")
    if attrs.get("aria-hidden", "").lower() == "true":
        soft.append("aria-hidden")
    classes = set(attrs.get("class", "").lower().split())
    hc = classes & HIDDEN_CLASSES
    if hc:
        hard.append("CSS-Klasse " + ", ".join(sorted(hc)))
    return hard, soft


def analyze_html_structure(text: str, hidden_base: float = 35.0, extra_css: str = "") -> list:
    findings = []
    css, toggles = _css_rules(text, extra_css)
    scripts = " ".join(m.group(1) for m in re.finditer(r"<script\b[^>]*>(.*?)</script\s*>", text, re.S | re.I))
    stack = []  # dicts: tag, start, open_end, hidden, soft, bg, reported
    pos = 0
    n = len(text)

    def close(el, end_inner, end_outer):
        if (el["hidden"] or el["soft"]) and not el["ancestor_hidden"]:
            inner = strip_tags(text[el["open_end"]:end_inner])
            if el["hidden"] and el.get("toggle"):
                ps, hits = payload_score(inner)
                if not inner.strip():
                    return
                findings.append(Finding(
                    category="hidden" if hits else "info",
                    rule="html.toggle_content",
                    title=f"Umschaltbarer Inhalt <{el['tag']}> (Reiter/Unterseite/Aufklappbereich)",
                    description=("Dieser Bereich ist erst nach einem Klick sichtbar (" + el["toggle"] +
                                 "). Er gehört zur normalen Seite und wird nicht als versteckt gewertet." + _payload_note(hits)),
                    score=max(45.0, ps) if hits else 5.0,
                    evidence=visible_repr(text[el["start"]:end_outer][:400]),
                    decoded=inner[:3000],
                    location=Location(start=el["start"], end=end_outer, line=line_of(text, el["start"])),
                    default_remove=bool(hits),
                    tags=["toggle"] + (["injection"] if hits else []),
                ))
                return
            if el["hidden"]:
                f = _hidden_finding(text, el["start"], end_outer, inner, "html.hidden_element",
                                    f"Versteckter HTML-Inhalt <{el['tag']}>",
                                    "Das Element wird durch " + "; ".join(el["hidden"]) +
                                    " für Menschen unsichtbar gemacht, bleibt aber für KI-Modelle lesbar.", base=hidden_base)
            else:
                f = _hidden_finding(text, el["start"], end_outer, inner, "html.low_visibility",
                                    f"Kaum sichtbarer HTML-Inhalt <{el['tag']}>",
                                    "Der Text ist schwer zu erkennen: " + "; ".join(el["soft"]) + ".", base=22.0, soft=True)
            if f:
                findings.append(f)

    while pos < n:
        m = TAG_RE.search(text, pos)
        if not m:
            break
        pos = m.end()
        tok = m.group(0)
        if tok.startswith("<!--"):
            continue
        closing, tag, rawattrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            idx = None
            for k in range(len(stack) - 1, -1, -1):
                if stack[k]["tag"] == tag:
                    idx = k
                    break
            if idx is None:
                continue
            while len(stack) > idx:
                el = stack.pop()
                if el["tag"] == tag:
                    close(el, m.start(), m.end())
                else:
                    close(el, m.start(), m.start())
            continue
        attrs = _attrs(rawattrs)
        props = _element_props(tag, attrs, css, [e["info"] for e in stack])
        parent_bg = stack[-1]["bg"] if stack else None
        bg = background_of(props) or parent_bg
        hard, soft = hiding_reasons(props, bg if bg is not None else (255, 255, 255))
        h2, s2 = _hidden_by_attrs(tag, attrs)
        hard += h2
        soft += s2
        # toggled tabs/sub-pages are normal content: hidden things *inside* them must still be found
        ancestor_hidden = any((e["hidden"] and not e.get("toggle")) or e["soft"] for e in stack)
        toggle = ""
        if hard and all(h.startswith(("display:none", "visibility", "hidden-Attribut", "CSS-Klasse")) for h in hard):
            classes = set(attrs.get("class", "").lower().split())
            if classes & toggles:
                toggle = "CSS-Zustand ." + "/.".join(sorted(classes & toggles))
            elif scripts and ((attrs.get("id") and attrs["id"] in scripts) or
                              any(len(c) > 3 and c in scripts for c in classes)):
                toggle = "per Skript umgeschaltet"
        # Text colour is inherited: an inherited invisible colour is reported on the ancestor.
        if tag == "input" and attrs.get("type", "").lower() == "hidden" and attrs.get("value"):
            ps, hits = payload_score(attrs["value"])
            if hits:
                findings.append(Finding(
                    category="hidden", rule="html.hidden_input", title="Anweisung in verstecktem Formularfeld",
                    description="Ein <input type=hidden> enthält Text." + _payload_note(hits),
                    score=min(100.0, ps + 20), evidence=visible_repr(tok), decoded=attrs["value"],
                    location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())), tags=["hidden"]))
        if tag in VOID or selfclose:
            continue
        if tag in RAW_TEXT:
            endm = re.compile(r"</" + tag + r"\s*>", re.I).search(text, pos)
            end = endm.end() if endm else n
            pos = end
            continue
        info = {"tag": tag, "classes": frozenset(attrs.get("class", "").lower().split()),
                "ids": frozenset([attrs["id"].lower()] if attrs.get("id") else [])}
        stack.append({"tag": tag, "start": m.start(), "open_end": m.end(), "hidden": hard, "soft": soft,
                      "bg": bg, "ancestor_hidden": ancestor_hidden, "info": info, "toggle": toggle})
    while stack:
        el = stack.pop()
        close(el, n, n)
    return findings


_STRUCTURAL_ATTRS = {"class", "id", "style", "href", "src", "srcset", "type", "rel", "name", "lang", "dir", "role",
                     "width", "height", "viewbox", "d", "points", "transform", "fill", "stroke", "xmlns", "charset",
                     "http-equiv", "sizes", "media", "integrity", "crossorigin", "action", "method", "target",
                     "for", "tabindex", "colspan", "rowspan", "align", "valign", "border", "cellpadding", "cellspacing"}


def analyze_attributes(text: str) -> list:
    """Alt texts, titles, aria-labels and meta contents are invisible but read by LLMs."""
    findings = []
    for m in TAG_RE.finditer(text):
        if m.group(0).startswith("<!--") or m.group(1):
            continue
        attrs = _attrs(m.group(3))
        for key, val in attrs.items():
            if not val or key in _STRUCTURAL_ATTRS or key.startswith("on") or len(val.split()) < 3:
                continue
            ps, hits = payload_score(val)
            if hits:
                findings.append(Finding(
                    category="hidden", rule="html.attribute", title=f"Anweisung im Attribut „{key}“",
                    description=f"Das {key}-Attribut von <{m.group(2)}> wird nicht als Fließtext angezeigt." + _payload_note(hits),
                    score=min(100.0, ps + 15), evidence=visible_repr(m.group(0)[:400]), decoded=val,
                    location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())), tags=["hidden"]))
    return findings


_PLACEHOLDER = re.compile(r"\{|\}|\$|%7b|%7d|\[|\]|<|>|%3c|\b(data|insert|secret|prompt|conversation|query|chat|history|summary|password|token|key|info|user_?input)\b", re.I)


def _url_risk(url: str) -> tuple:
    q = url.split("?", 1)[1] if "?" in url else ""
    path = url.split("://", 1)[-1].split("/", 1)[-1] if "/" in url.split("://", 1)[-1] else ""
    if _PLACEHOLDER.search(q) or re.search(r"\{|\}|%7b|\$", path, re.I):
        return 75.0, "Die URL enthält Platzhalter/Parameter, in die ein Modell Gesprächsdaten einsetzen soll."
    if len(q) > 40:
        return 25.0, "Externe Bild-URL mit langen Parametern – Bilder werden oft automatisch geladen (Datenabfluss möglich)."
    return 0.0, ""


def analyze_markdown(text: str) -> list:
    findings = []
    # Markdown comment idioms: [//]: # (hidden), [comment]: <> (hidden)
    for m in re.finditer(r"(?m)^[ \t]*\[(?://|#|comment|hidden|note|_)?[^\]\n]*\]:[ \t]*(?:#|<>|<#>)[ \t]*(?:\((.*)\)|\"(.*)\"|'(.*)')[ \t]*$", text):
        inner = next((g for g in m.groups() if g is not None), "")
        f = _hidden_finding(text, m.start(), m.end(), inner, "md.comment_link", "Versteckter Markdown-Kommentar",
                            "Ein Link-Referenz-Kommentar ([//]: # (…)) wird beim Rendern nicht angezeigt.", base=28.0)
        if f:
            findings.append(f)
    # Front matter (not rendered on most platforms)
    fm = re.match(r"\A(?:\ufeff)?---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", text, re.S)
    if fm:
        ps, hits = payload_score(fm.group(1))
        if hits:
            findings.append(Finding(
                category="hidden", rule="md.front_matter", title="Anweisung im Front-Matter",
                description="YAML-Front-Matter wird meist nicht gerendert, aber vom Modell gelesen." + _payload_note(hits),
                score=min(100.0, ps + 15), evidence=visible_repr(fm.group(0)[:500]), decoded=fm.group(1),
                location=Location(start=fm.start(1), end=fm.end(1), line=line_of(text, fm.start(1))), tags=["hidden"]))
    # Images: exfiltration channel and alt texts
    for m in re.finditer(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'(]([^\"')]*)[\"')])?\s*\)", text):
        alt, url, title = m.group(1), m.group(2), m.group(3) or ""
        if re.match(r"https?://", url, re.I):
            score, why = _url_risk(url)
            if score:
                findings.append(Finding(
                    category="exfil", rule="md.image_exfil", title="Mögliche Datenabfluss-URL in Markdown-Bild",
                    description=why, score=score, evidence=visible_repr(m.group(0)[:400]),
                    location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())), tags=["exfil"]))
        for label, val in (("Alt-Text", alt), ("Bildtitel", title)):
            ps, hits = payload_score(val)
            if hits:
                findings.append(Finding(
                    category="hidden", rule="md.image_text", title=f"Anweisung im {label} eines Bildes",
                    description=f"Der {label} wird meist nicht angezeigt, aber vom Modell gelesen." + _payload_note(hits),
                    score=min(100.0, ps + 15), evidence=visible_repr(m.group(0)[:400]), decoded=val,
                    location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())), tags=["hidden"]))
    # Link targets
    for m in re.finditer(r"(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'(]([^\"')]*)[\"')])?\s*\)", text):
        url, title = m.group(2), m.group(3) or ""
        if re.match(r"\s*(javascript:|vbscript:|data:text/html)", url, re.I):
            findings.append(Finding(
                category="active", rule="md.script_link", title="Skript-Link in Markdown",
                description="Der Link führt Code aus (javascript:/data:).", score=45.0,
                evidence=visible_repr(m.group(0)[:300]),
                location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start()))))
        ps, hits = payload_score(title)
        if hits:
            findings.append(Finding(
                category="hidden", rule="md.link_title", title="Anweisung im Link-Titel",
                description="Der Titel eines Links ist nur als Tooltip sichtbar." + _payload_note(hits),
                score=min(100.0, ps + 15), evidence=visible_repr(m.group(0)[:300]), decoded=title,
                location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())), tags=["hidden"]))
    # Reference definitions with titles
    for m in re.finditer(r"(?m)^[ \t]{0,3}\[([^\]\n]+)\]:[ \t]*<?(\S+?)>?(?:[ \t]+[\"'(](.*)[\"')])?[ \t]*$", text):
        title = m.group(3) or ""
        url = m.group(2)
        ps, hits = payload_score(title + " " + m.group(1))
        if hits and url not in ("#", "<>"):
            findings.append(Finding(
                category="hidden", rule="md.reference", title="Anweisung in Link-Referenz-Definition",
                description="Referenz-Definitionen werden nicht gerendert." + _payload_note(hits),
                score=min(100.0, ps + 15), evidence=visible_repr(m.group(0)), decoded=title,
                location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())), tags=["hidden"]))
    return findings


_LATEX_WHITE = r"(?:white|#?fff(?:fff)?|ffffff|snow|ivory|whitesmoke|transparent)"


def analyze_latex(text: str) -> list:
    findings = []
    pats = [
        (r"\\(?:textcolor|color)\s*\{\s*" + _LATEX_WHITE + r"\s*\}\s*\{([^{}]*)\}", "LaTeX-Text in weißer Farbe"),
        (r"\\color\s*\{\s*" + _LATEX_WHITE + r"\s*\}([^${}]*)", "LaTeX-Text in weißer Farbe"),
        (r"\\(?:phantom|hphantom|vphantom)\s*\{([^{}]*)\}", "LaTeX-\\phantom (unsichtbar)"),
        (r"\\(?:fontsize\s*\{\s*0*\.?\d\s*(?:pt)?\s*\}\s*\{[^}]*\}\\selectfont)\s*([^\n$]*)", "LaTeX-Winzschrift"),
    ]
    for pat, title in pats:
        for m in re.finditer(pat, text, re.I):
            f = _hidden_finding(text, m.start(), m.end(), m.group(1), "latex.hidden", title,
                                "Formel-/LaTeX-Befehle machen den Text unsichtbar.", base=32.0)
            if f:
                findings.append(f)
    return findings


def analyze_comments(text: str) -> list:
    findings = []
    for m in re.finditer(r"<!--(.*?)(?:-->|\Z)", text, re.S):
        inner = m.group(1).strip()
        f = _hidden_finding(text, m.start(), m.end(), inner, "markup.comment", "Versteckter HTML-Kommentar",
                            "HTML-Kommentare werden nicht angezeigt, aber von KI-Modellen mitgelesen.", base=15.0)
        if f:
            findings.append(f)
    return findings


def active_content(text: str, is_html: bool = False) -> list:
    findings = []
    for m in re.finditer(r"<(script|iframe|object|embed|form|meta\s+http-equiv\s*=\s*[\"']?refresh)\b", text, re.I):
        tag = m.group(1).split()[0].lower()
        findings.append(Finding(
            category="active", rule=f"markup.{tag}", title=f"Aktiver Inhalt <{tag}>",
            description="Aktive Inhalte können Daten nachladen oder senden und gehören nicht in reine Text-Dokumente.",
            score=(12.0 if is_html else 30.0) if tag != "meta" else (12.0 if is_html else 25.0), evidence=context(text, m.start(), m.end()),
            location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())),
            removable=False, default_remove=False))
    return findings


def mask_markdown_code(text: str) -> str:
    """Blank out fenced/indented code blocks and inline code spans (offsets preserved).

    HTML inside code is displayed literally by Markdown renderers, so it is not
    hidden content."""
    def blank(m):
        return "".join(c if c in "\r\n" else " " for c in m.group(0))
    text = re.sub(r"(?ms)^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]{0,3}\1[ \t]*$|\Z)", blank, text)
    text = re.sub(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", blank, text, flags=re.S)
    return text


def analyze_markup(text: str, is_html: bool, extra_css: str = "") -> list:
    findings = []
    src = text if is_html else mask_markdown_code(text)
    findings += analyze_comments(src)
    findings += analyze_html_structure(src, hidden_base=18.0 if is_html else 35.0, extra_css=extra_css)
    findings += analyze_attributes(src)
    findings += analyze_latex(src)
    findings += active_content(src, is_html)
    if not is_html:
        findings += analyze_markdown(src)
    # evidence must show the real text, not the masked one
    for f in findings:
        if f.location.start is not None and src is not text:
            f.evidence = visible_repr(text[f.location.start:f.location.end][:500])
    return findings
