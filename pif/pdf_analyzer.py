"""PDF analysis based on PyMuPDF.

For every text span the analyzer decides whether a human can actually see it:

  * render mode 3/7 (invisible text), opacity ~0,
  * tiny or horizontally squashed glyphs,
  * text outside the visible page area,
  * text colour ~ background colour (white on white, light grey) - measured on
    the *rendered* page, so coloured boxes and images are taken into account,
  * text that is painted over by later images/vector shapes or clipped away
    (the glyph colour does not appear in the rendered pixels).

Additionally annotations, form fields, links, metadata, JavaScript, launch
actions and embedded files are inspected, and the complete text layer (what an
LLM receives) runs through the text analyzer.
"""
from __future__ import annotations

import re

import numpy as np
import pymupdf

from .css import contrast_ratio
from .i18n import T, join
from .models import Finding, Location
from .patterns import payload_score
from .text_analyzer import _payload_note, analyze_text, visible_repr

MAX_RENDER_PX = 2600


def _rgb(color, colorspace) -> tuple:
    if color is None:
        return (0, 0, 0)
    c = tuple(color)
    if len(c) == 1:
        v = c[0] * 255
        return (v, v, v)
    if len(c) == 3:
        return tuple(x * 255 for x in c)
    if len(c) == 4:  # CMYK
        cc, m, y, k = c
        return ((1 - cc) * (1 - k) * 255, (1 - m) * (1 - k) * 255, (1 - y) * (1 - k) * 255)
    return (0, 0, 0)


class _PageRaster:
    def __init__(self, page):
        rect = page.rect
        self.zoom = min(2.0, MAX_RENDER_PX / max(rect.width, rect.height, 1))
        self.matrix = page.rotation_matrix * pymupdf.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(self.zoom, self.zoom), alpha=False, colorspace=pymupdf.csRGB,
                              annots=False)
        self.arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        self.h, self.w = self.arr.shape[:2]

    def region(self, r: pymupdf.Rect, margin: int = 0):
        rr = r * self.matrix
        x0 = max(0, int(rr.x0) - margin)
        y0 = max(0, int(rr.y0) - margin)
        x1 = min(self.w, int(rr.x1 + 0.999) + margin)
        y1 = min(self.h, int(rr.y1 + 0.999) + margin)
        if x1 <= x0 or y1 <= y0:
            return None
        return self.arr[y0:y1, x0:x1]


def _background(region) -> tuple:
    flat = region.reshape(-1, 3)
    if len(flat) > 40000:
        flat = flat[:: len(flat) // 40000 + 1]
    q = (flat // 8).astype(np.int32)
    packed = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
    vals, counts = np.unique(packed, return_counts=True)
    mode = vals[np.argmax(counts)]
    sel = flat[packed == mode]
    return tuple(float(x) for x in sel.mean(axis=0))


def _presence(region, rgb, tol=90.0) -> float:
    flat = region.reshape(-1, 3).astype(np.int16)
    d = np.abs(flat - np.array(rgb, dtype=np.int16)).max(axis=1)
    return float((d <= tol).mean())


def _ink(region, bg, tol=48.0) -> float:
    flat = region.reshape(-1, 3).astype(np.int16)
    d = np.abs(flat - np.array(bg, dtype=np.int16)).max(axis=1)
    return float((d > tol).mean())


def _merge_rects(chars) -> list:
    """chars: list of (page, Rect). Merge horizontally adjacent glyph boxes per line."""
    out = []
    cur = None
    for page, r in chars:
        if r.is_empty or r.width <= 0:
            continue
        if cur and cur[0] == page and abs(cur[1].y0 - r.y0) < 1.5 and abs(cur[1].y1 - r.y1) < 1.5 and -1 <= r.x0 - cur[1].x1 < 6:
            cur[1] |= r
        else:
            if cur:
                out.append(cur)
            cur = [page, pymupdf.Rect(r)]
    if cur:
        out.append(cur)
    return out


class PdfDocModel:
    """Text layer of the whole document with per-character geometry."""

    def __init__(self):
        self.chars = []       # str
        self.pages = []       # page number per char (or -1 for synthetic)
        self.rects = []       # pymupdf.Rect per char (or None)
        self.hidden = []      # list of hard reasons (empty -> visible)
        self.soft = []        # list of low-visibility reasons
        self.page_info = []   # dicts: width, height, rotation

    def add(self, ch, page, rect, hard, soft):
        self.chars.append(ch)
        self.pages.append(page)
        self.rects.append(rect)
        self.hidden.append(hard)
        self.soft.append(soft)

    @property
    def text(self) -> str:
        return "".join(self.chars)


def _span_text(span) -> str:
    return "".join(chr(c[0]) if c[0] >= 0 else "�" for c in span["chars"])


def _twin_key(span) -> tuple:
    b = span["bbox"]
    return (_span_text(span), round(b[0]), round(b[1]), round(b[2]), round(b[3]))


def _analyze_page(page, pno, model: PdfDocModel, stats: dict, render_page=None, off_layers=frozenset()):
    """``page`` provides the text (all layers switched on), ``render_page`` what a human sees."""
    rect = page.rect
    try:
        trace = page.get_texttrace()
    except Exception:
        trace = []
    if not trace:
        return
    raster = _PageRaster(render_page or page)
    bboxlog = page.get_bboxlog()
    # Opaque things painted later in the content stream can cover earlier text.
    occluders = [(i, pymupdf.Rect(b)) for i, (kind, b) in enumerate(bboxlog)
                 if kind in ("fill-image", "fill-shade", "fill-imgmask")]
    try:
        for d in page.get_drawings():
            if d.get("fill") is not None and (d.get("fill_opacity") or 1.0) >= 0.9 and d.get("seqno") is not None:
                occluders.append((d["seqno"], pymupdf.Rect(d["rect"])))
    except Exception:
        occluders += [(i, pymupdf.Rect(b)) for i, (kind, b) in enumerate(bboxlog) if kind == "fill-path"]
    text_boxes = [(s["seqno"], pymupdf.Rect(s["bbox"])) for s in trace if _span_text(s).strip()]
    unrot = page.cropbox if page.rotation else rect

    # OCR detection: almost all text invisible and the page is mostly an image.
    total = sum(len(s["chars"]) for s in trace)
    invis = sum(len(s["chars"]) for s in trace if s["type"] in (3, 7))
    img_area = 0.0
    try:
        for info in page.get_image_info():
            img_area += abs(pymupdf.Rect(info["bbox"]) & rect)
    except Exception:
        pass
    is_ocr = total > 0 and invis / total >= 0.8 and img_area >= 0.5 * abs(rect)
    if is_ocr:
        stats["ocr_pages"].append(pno + 1)

    # Fill+stroke text appears as two congruent spans ("twins"), e.g. white fill with a
    # black outline. The glyphs are visible if any twin is.
    twins = {}
    for s in trace:
        twins.setdefault(_twin_key(s), []).append(s)
    emitted = set()

    prev = None  # (origin_y, x_end, size)
    for span in trace:
        text = _span_text(span)
        sb = pymupdf.Rect(span["bbox"])
        key = _twin_key(span)
        if key in emitted:
            continue  # same glyphs already analysed via their twin
        emitted.add(key)
        siblings = twins[key]
        size = float(span.get("size") or 0)
        hard, soft = [], []
        has_ink_chars = bool(text.strip())
        if has_ink_chars:
            ttype = span.get("type", 0)
            if span.get("layer") and span["layer"] in off_layers:
                hard.append(T(f"on hidden PDF layer “{span['layer']}”", f"auf ausgeblendeter PDF-Ebene „{span['layer']}“"))
            if ttype in (3, 7) and not is_ocr:
                hard.append(T("invisible render mode (Tr 3)", "unsichtbarer Rendermodus (Tr 3)"))
            op = span.get("opacity")
            if op is not None and op <= 0.05:
                hard.append(T(f"transparency {op:.2f}", f"Transparenz {op:.2f}"))
            horizontal = abs(span["dir"][1]) < 0.1
            glyph_h = sb.height if horizontal else sb.width
            n_ink = max(1, len(text.strip()))
            if size < 1.5 or glyph_h < 1.5:
                hard.append(T(f"tiny font ({size:.1f} pt)", f"winzige Schrift ({size:.1f} pt)"))
            elif size < 4.0:
                soft.append(T(f"very small font ({size:.1f} pt)", f"sehr kleine Schrift ({size:.1f} pt)"))
            if horizontal and len(text) >= 3 and sb.width / len(text) < 0.35:
                hard.append(T("squashed horizontally", "horizontal zusammengestaucht"))
            visible_area = sb & unrot
            if sb.is_empty or abs(sb) == 0:
                pass
            elif visible_area.is_empty:
                hard.append(T("outside the visible page", "außerhalb der sichtbaren Seite"))
            elif abs(visible_area) < 0.5 * abs(sb):
                soft.append(T("partly outside the page", "teilweise außerhalb der Seite"))
            if not hard and ttype not in (3, 7) and not visible_area.is_empty:
                reg = raster.region(visible_area, margin=2)
                inner = raster.region(visible_area)
                if reg is not None and inner is not None and inner.size > 0:
                    bg = _background(reg)
                    rgb = _rgb(span.get("color"), span.get("colorspace"))
                    ratio = contrast_ratio(rgb, bg)
                    for sib in siblings:
                        if sib is not span and sib.get("type", 0) not in (3, 7):
                            ratio = max(ratio, contrast_ratio(_rgb(sib.get("color"), sib.get("colorspace")), bg))
                    if ratio < 1.3:
                        hard.append(T(f"text colour matches background (contrast {ratio:.2f}:1)",
                                      f"Textfarbe entspricht Hintergrund (Kontrast {ratio:.2f}:1)"))
                    elif ratio < 1.9:
                        soft.append(T(f"very low contrast ({ratio:.2f}:1)", f"sehr schwacher Kontrast ({ratio:.2f}:1)"))
                    else:
                        pres = _presence(inner, rgb)
                        ink = _ink(inner, bg)
                        later = [(i, r) for i, r in occluders if i > span["seqno"] and r.intersects(sb)]
                        cover = [i for i, r in later if (r + (-1, -1, 1, 1)).contains(sb)]
                        if not cover and later:
                            # several shapes together may cover the text
                            covered_area = sum(abs(r & sb) for _, r in later)
                            if covered_area >= 0.97 * abs(sb):
                                cover = [i for i, _ in later]
                        if cover:
                            # Ink found in the region may come from text painted *on top* of the cover.
                            first = min(cover)
                            overdrawn = any(q > first and abs(qr & sb) > 0.2 * abs(sb)
                                            for q, qr in text_boxes)
                            if pres < 0.003 or overdrawn:
                                hard.append(T("covered by a graphic/image", "von Grafik/Bild verdeckt"))
                        elif pres < 0.003 and size >= 6 and ink < 0.003:
                            hard.append(T("clipped / not rendered", "abgeschnitten / nicht gerendert"))
        # build text layer with geometry
        for c in span["chars"]:
            ch = chr(c[0]) if c[0] >= 0 else "�"
            origin = c[2]
            r = pymupdf.Rect(c[3])
            if prev is not None:
                py_, px_end, psize = prev
                new_line = (abs(origin[1] - py_) > max(2.0, 0.5 * max(psize, size))
                            or origin[0] < px_end - 3 * max(size, 1))
                if new_line:
                    if model.chars and model.chars[-1] != "\n":
                        model.add("\n", -1, None, [], [])
                elif origin[0] - px_end > 0.22 * max(size, 1) and model.chars and not model.chars[-1].isspace() and not ch.isspace():
                    model.add(" ", -1, None, [], [])
            model.add(ch, pno, r, hard if not ch.isspace() else [], soft if not ch.isspace() else [])
            prev = (origin[1], r.x1, size)


def _segments(model: PdfDocModel, which: str) -> list:
    """Group consecutive hidden characters (allowing whitespace in between)."""
    flags = model.hidden if which == "hard" else model.soft
    segs = []
    n = len(model.chars)
    i = 0
    while i < n:
        if flags[i] and (which == "hard" or not model.hidden[i]):
            j = i
            last = i
            key = set(flags[i])
            while j < n:
                if flags[j] and (which == "hard" or not model.hidden[j]):
                    if set(flags[j]) != key:
                        break
                    last = j
                    j += 1
                elif model.chars[j].isspace() and j - last < 3:
                    j += 1
                else:
                    break
            segs.append((i, last + 1))
            i = last + 1
        else:
            i += 1
    return segs


def _location_for(model: PdfDocModel, s: int, e: int, page_sizes) -> Location:
    chars = [(model.pages[k], model.rects[k]) for k in range(s, e) if model.rects[k] is not None]
    merged = _merge_rects(chars)
    rects = [[p, r.x0, r.y0, r.x1, r.y1] for p, r in merged]
    view = []
    for p, r in merged:
        info = page_sizes[p]
        rr = r * info["matrix"]
        view.append([p, max(0, rr.x0 / info["w"]), max(0, rr.y0 / info["h"]), min(1, rr.x1 / info["w"]), min(1, rr.y1 / info["h"])])
    page = merged[0][0] if merged else None
    return Location(start=s, end=e, page=page, rects=rects, view_rects=view, target="pdf_text",
                    line=(page + 1) if page is not None else None)


_REASON_TITLES = [
    ("text colour matches", T("Invisible text: font colour = background colour (e.g. white on white)",
                              "Unsichtbarer Text: Schriftfarbe = Hintergrundfarbe (z. B. weiß auf weiß)")),
    ("invisible render mode", T("Invisible text (PDF render mode 3)", "Unsichtbarer Text (PDF-Rendermodus 3)")),
    ("tiny font", T("Invisible text: tiny font size", "Unsichtbarer Text: winzige Schriftgröße")),
    ("squashed", T("Invisible text: squashed to zero width", "Unsichtbarer Text: auf Nullbreite gestaucht")),
    ("outside the visible", T("Invisible text outside the page", "Unsichtbarer Text außerhalb der Seite")),
    ("covered by", T("Covered text (under an image/graphic)", "Verdeckter Text (unter Bild/Grafik)")),
    ("clipped", T("Invisible text: clipped / not rendered", "Unsichtbarer Text: abgeschnitten / nicht gerendert")),
    ("transparency", T("Invisible text: fully transparent", "Unsichtbarer Text: vollständig transparent")),
    ("hidden PDF layer", T("Invisible text on a hidden PDF layer", "Unsichtbarer Text auf ausgeblendeter PDF-Ebene")),
]


def _title_for(reasons) -> str:
    for key, title in _REASON_TITLES:
        if any(key in str(r) for r in reasons):
            return title
    return T("Hidden text in the PDF", "Versteckter Text im PDF")


def _hidden_findings(model: PdfDocModel, page_sizes) -> tuple:
    findings = []
    covered = []
    text = model.text
    for which in ("hard", "soft"):
        for s, e in _segments(model, which):
            seg = text[s:e]
            letters = sum(1 for c in seg if c.isalnum())
            if letters < 2:
                continue
            reasons = []
            for k in range(s, e):
                for r in (model.hidden[k] if which == "hard" else model.soft[k]):
                    if r not in reasons:
                        reasons.append(r)
            words = len(seg.split())
            ps, hits = payload_score(seg)
            if which == "hard":
                base = 30.0 if words < 3 else 50.0 if words < 15 else 58.0
                score = max(base, min(100.0, ps + 28)) if hits else base
                title = _title_for(reasons)
            else:
                base = 15.0 if words < 3 else 25.0
                score = max(base, min(100.0, ps + 18)) if hits else base
                title = T("Barely visible text (light grey/very small)", "Kaum sichtbarer Text (hellgrau/sehr klein)")
            loc = _location_for(model, s, e, page_sizes)
            findings.append(Finding(
                category="hidden",
                rule=f"pdf.hidden_{which}",
                title=title,
                description=(T("Not visible to humans, normally readable for AI models. Reasons: ",
                                "Für Menschen nicht sichtbar, für KI-Modelle normal lesbar. Gründe: ") if which == "hard"
                             else T("Hard to see for humans. Reasons: ", "Für Menschen schwer zu erkennen. Gründe: "))
                + join("; ", reasons[:6]) + "." + _payload_note(hits),
                score=score,
                evidence=visible_repr(seg, 800),
                decoded=seg[:4000],
                location=loc,
                default_remove=which == "hard" or bool(hits),
                tags=["hidden"] + (["injection"] if hits else []),
            ))
            covered.append((s, e, findings[-1]))
    return findings, covered


def _xref_scan(doc) -> list:
    findings = []
    js_snippets = []
    launch = []
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=False)
        except Exception:
            continue
        if "/JS" in obj or "/JavaScript" in obj:
            m = re.search(r"/JS\s*\((.*?)\)\s*[/>]", obj, re.S)
            if m:
                js_snippets.append(m.group(1)[:500])
            else:
                m = re.search(r"/JS\s+(\d+)\s+0\s+R", obj)
                if m:
                    try:
                        js_snippets.append(doc.xref_stream(int(m.group(1))).decode("latin-1", "replace")[:500])
                    except Exception:
                        js_snippets.append("(JavaScript stream)")
                elif "/S /JavaScript" in obj or "/S/JavaScript" in obj:
                    js_snippets.append("(JavaScript action)")
        if "/Launch" in obj:
            launch.append(xref)
    if js_snippets:
        ps, hits = payload_score(" ".join(js_snippets))
        findings.append(Finding(
            category="active", rule="pdf.javascript", title=T("JavaScript in the PDF", "JavaScript im PDF"),
            description=T(f"{len(js_snippets)} JavaScript action(s). Scripts can change content dynamically or send data.",
                          f"{len(js_snippets)} JavaScript-Aktion(en). Skripte können Inhalte dynamisch verändern oder "
                          "Daten senden.")
                        + _payload_note(hits),
            score=max(40.0, ps + 10), evidence=visible_repr("\n---\n".join(js_snippets), 800),
            location=Location(target="pdf_js"), default_remove=True))
    if launch:
        findings.append(Finding(
            category="active", rule="pdf.launch",
            title=T("Launch action (starts programs/files)", "Launch-Aktion (startet Programme/Dateien)"),
            description=T("The PDF contains /Launch actions that can open external programs or files.",
                          "Das PDF enthält /Launch-Aktionen, die externe Programme oder Dateien öffnen können."),
            score=60.0, evidence=f"Objekte: {launch[:10]}", location=Location(target="pdf_js"), default_remove=True))
    return findings


def _annotation_findings(doc, page_sizes) -> list:
    findings = []
    for pno, page in enumerate(doc):
        try:
            annots = list(page.annots() or [])
        except Exception:
            annots = []
        for a in annots:
            info = a.info or {}
            parts = [info.get("content", ""), info.get("title", ""), info.get("subject", "")]
            try:
                if a.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT:
                    parts.append(page.get_textbox(a.rect))
            except Exception:
                pass
            txt = "\n".join(p for p in parts if p)
            flags = a.flags
            hidden = bool(flags & (pymupdf.PDF_ANNOT_IS_HIDDEN | pymupdf.PDF_ANNOT_IS_NO_VIEW))
            ps, hits = payload_score(txt)
            if not hits and not (hidden and len(txt.split()) >= 3):
                continue
            score = min(100.0, ps + 15) if hits else 30.0
            r = a.rect
            info_p = page_sizes[pno]
            rr = r * info_p["matrix"]
            findings.append(Finding(
                category="hidden", rule="pdf.annotation",
                title=(T(f"Instruction in a PDF annotation ({a.type[1]})", f"Anweisung in PDF-Annotation ({a.type[1]})")
                       if hits else T(f"Hidden PDF annotation ({a.type[1]})", f"Versteckte PDF-Annotation ({a.type[1]})")),
                description=(T("Comments/notes are often shown collapsed, but text extractors read them.",
                               "Kommentare/Notizen werden oft eingeklappt angezeigt, aber von Text-Extraktoren gelesen.")
                             + (T(" The annotation is flagged as hidden.", " Die Annotation ist als versteckt markiert.")
                                if hidden else "") + _payload_note(hits)),
                score=score, evidence=visible_repr(txt, 600), decoded=txt,
                location=Location(page=pno, line=pno + 1, xref=a.xref, target="pdf_annot",
                                  rects=[[pno, r.x0, r.y0, r.x1, r.y1]],
                                  view_rects=[[pno, rr.x0 / info_p["w"], rr.y0 / info_p["h"], rr.x1 / info_p["w"], rr.y1 / info_p["h"]]]),
                tags=["hidden"]))
        try:
            widgets = list(page.widgets() or [])
        except Exception:
            widgets = []
        for w in widgets:
            txt = " ".join(str(x) for x in (w.field_value, w.field_label, getattr(w, "field_tooltip", "")) if x)
            ps, hits = payload_score(txt)
            if hits:
                findings.append(Finding(
                    category="hidden", rule="pdf.form_field",
                    title=T("Instruction in a PDF form field", "Anweisung in PDF-Formularfeld"),
                    description=T("Form field values/tooltips are often not visible.",
                                  "Formularfeld-Werte/Tooltips sind oft nicht sichtbar.") + _payload_note(hits),
                    score=min(100.0, ps + 15), evidence=visible_repr(txt, 600), decoded=txt,
                    location=Location(page=pno, line=pno + 1, xref=w.xref, target="pdf_annot"), tags=["hidden"]))
        for li, link in enumerate(page.get_links()):
            uri = link.get("uri") or ""
            if not uri:
                continue
            if re.match(r"\s*(javascript|vbscript):", uri, re.I):
                score, why = 50.0, T("The link executes JavaScript.", "Link führt JavaScript aus.")
            else:
                ps, hits = payload_score(uri)
                if re.search(r"\{|\}|%7b|\$\{", uri, re.I):
                    score, why = 55.0, T("The link URL contains placeholders (possible data exfiltration).",
                                         "Link-URL enthält Platzhalter (möglicher Datenabfluss).")
                elif hits:
                    score, why = min(100.0, ps + 10), T("The link URL contains injection text.",
                                                         "Link-URL enthält Injection-Text.") + _payload_note(hits)
                else:
                    continue
            findings.append(Finding(
                category="exfil", rule="pdf.link", title=T("Suspicious link in the PDF", "Verdächtiger Link im PDF"),
                description=why, score=score,
                evidence=visible_repr(uri, 400), location=Location(page=pno, line=pno + 1, xref=li, target="pdf_link")))
    return findings


def _metadata_findings(doc) -> list:
    findings = []
    meta = doc.metadata or {}
    txt = "\n".join(f"{k}: {v}" for k, v in meta.items() if v and k not in ("format", "encryption"))
    try:
        xmp = doc.get_xml_metadata() or ""
    except Exception:
        xmp = ""
    xmp_text = re.sub(r"<[^>]+>", " ", xmp)
    full = txt + "\n" + xmp_text
    ps, hits = payload_score(full)
    if hits:
        findings.append(Finding(
            category="hidden", rule="pdf.metadata", title=T("Instruction in PDF metadata", "Anweisung in PDF-Metadaten"),
            description=T("Title/author/keywords/XMP are not shown in the document, but some tools pass them to AI models.",
                          "Titel/Autor/Schlagwörter/XMP werden nicht im Dokument angezeigt, aber von manchen Tools an "
                          "KI-Modelle übergeben.")
                        + _payload_note(hits),
            score=min(100.0, ps + 15), evidence=visible_repr(full.strip(), 800), decoded=full.strip()[:3000],
            location=Location(target="pdf_meta"), tags=["hidden"]))
    return findings


def _embedded_findings(doc) -> list:
    findings = []
    try:
        names = doc.embfile_names()
    except Exception:
        names = []
    for name in names:
        try:
            data = doc.embfile_get(name)
        except Exception:
            data = b""
        txt = ""
        try:
            txt = data[:200000].decode("utf-8")
        except UnicodeDecodeError:
            pass
        ps, hits = payload_score(txt) if txt else (0.0, [])
        findings.append(Finding(
            category="active", rule="pdf.embedded_file", title=T(f"Embedded file “{name}”", f"Eingebettete Datei „{name}“"),
            description=T("The PDF contains an attached file that is easily overlooked.",
                          "Das PDF enthält eine angehängte Datei, die beim Lesen leicht übersehen wird.") + _payload_note(hits),
            score=min(100.0, ps + 15) if hits else 30.0, evidence=visible_repr(txt[:400]) if txt else f"{len(data)} Bytes",
            decoded=txt[:3000], location=Location(target="pdf_embedded"), tags=["hidden"]))
    return findings


def analyze_pdf(data: bytes):
    """Return (findings, text, stats)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    stats = {"pages": doc.page_count, "ocr_pages": [], "encrypted": bool(doc.needs_pass)}
    if doc.needs_pass and not doc.authenticate(""):
        raise ValueError("PDF is password protected / PDF ist passwortgeschützt")
    model = PdfDocModel()
    page_sizes = []
    # Text on switched-off layers (Optional Content) is skipped by PyMuPDF's extraction but
    # read by many other PDF libraries: analyse a copy with every layer switched on.
    off_layers = set()
    work = doc
    try:
        off_layers = {v["name"] for v in doc.get_ocgs().values() if not v.get("on", True)}
    except Exception:
        pass
    if off_layers:
        tmp = pymupdf.open(stream=data, filetype="pdf")
        if tmp.needs_pass:
            tmp.authenticate("")
        cat = tmp.pdf_catalog()
        tmp.xref_set_key(cat, "OCProperties/D/OFF", "[]")
        tmp.xref_set_key(cat, "OCProperties/D/BaseState", "/ON")
        tmp.xref_set_key(cat, "OCProperties/D/AS", "null")
        work = pymupdf.open(stream=tmp.tobytes(), filetype="pdf")
        stats["hidden_layers"] = sorted(off_layers)
    for pno, page in enumerate(doc):
        r = page.rect
        page_sizes.append({"w": r.width, "h": r.height, "matrix": page.rotation_matrix})
        if pno > 0:
            model.add("\n", -1, None, [], [])
            model.add("\n", -1, None, [], [])
        _analyze_page(work[pno], pno, model, stats, render_page=page, off_layers=frozenset(off_layers))
    text = model.text
    findings, covered = _hidden_findings(model, page_sizes)

    # Text-level analysis on the full text layer (exactly what an LLM gets).
    from .scanner import absorb_into_hidden
    text_findings = absorb_into_hidden(analyze_text(text, include_layout=False), hosts=[c[2] for c in covered])
    for f in text_findings:
        s, e = f.location.start or 0, f.location.end or 0
        loc = _location_for(model, s, e, page_sizes)
        loc.ranges = f.location.ranges
        f.location = loc
        findings.append(f)

    findings += _annotation_findings(doc, page_sizes)
    findings += _metadata_findings(doc)
    findings += _xref_scan(doc)
    findings += _embedded_findings(doc)

    stats["chars"] = sum(1 for c in model.chars if not c.isspace())
    stats["hidden_chars"] = sum(1 for k, c in enumerate(model.chars) if model.hidden[k] and not c.isspace())
    stats["page_sizes"] = [[p["w"], p["h"]] for p in page_sizes]
    doc.close()
    return findings, text, stats
