"""Remove selected findings from documents and export the results."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re

from .models import ScanResult
from .scanner import decode_text, scan_bytes


def _edits_for(findings) -> list:
    edits = []
    for f in findings:
        loc = f.location
        if loc.ranges:
            for s, e, rep in loc.ranges:
                edits.append((s, e, rep if f.action == "replace" else ""))
        elif loc.start is not None and loc.end is not None:
            edits.append((loc.start, loc.end, f.replacement if f.action == "replace" else ""))
    return edits


def apply_edits(text: str, edits) -> str:
    """Apply (start, end, replacement) edits. Overlaps are merged; deletion wins."""
    if not edits:
        return text
    edits = sorted(edits, key=lambda x: (x[0], -x[1]))
    merged = []
    for s, e, rep in edits:
        if merged and s < merged[-1][1]:
            ps, pe, prep = merged[-1]
            if e <= pe:
                # fully contained: the outer edit decides, unless the outer one is a
                # replacement and the inner one a deletion of the same span.
                continue
            merged[-1] = (ps, e, "")
        else:
            merged.append((s, e, rep))
    out = []
    pos = 0
    for s, e, rep in merged:
        left = text[pos:s]
        if not rep and e > s:
            # Avoid "word  word" or dangling blank lines at the seam of a deletion.
            right = text[e:e + 1]
            prev = out[-1] if not left and out else left
            if right in (" ", "\t") and (prev.endswith((" ", "\t")) or not prev or prev.endswith("\n")):
                e += 1
            elif right == "\n" and (prev.endswith("\n") or not prev):
                t = min(2, len(prev) - len(prev.rstrip("\n"))) if prev else 2
                r = len(text[e:]) - len(text[e:].lstrip("\n"))
                if r and t:
                    e += min(r, max(1, t + r - 2))
        out.append(left)
        out.append(rep)
        pos = e
    out.append(text[pos:])
    return "".join(out)


def select(result: ScanResult, ids=None) -> list:
    if ids is None:
        return [f for f in result.findings if f.removable and f.default_remove]
    ids = set(ids)
    return [f for f in result.findings if f.id in ids and f.removable]


def clean_text(text: str, findings) -> str:
    return apply_edits(text, _edits_for([f for f in findings if f.location.target == "text"]))


def _encode(text: str, encoding: str) -> bytes:
    enc = encoding or "utf-8"
    try:
        return text.encode(enc)
    except (UnicodeEncodeError, LookupError):
        return text.encode("utf-8")


def clean_pdf(data: bytes, findings) -> bytes:
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    if doc.needs_pass:
        doc.authenticate("")
    redact_pages = set()
    annot_xrefs = {}
    link_idx = {}
    scrub_js = scrub_emb = scrub_meta = False
    for f in findings:
        loc = f.location
        if loc.target == "pdf_text":
            for p, x0, y0, x1, y1 in loc.rects:
                r = pymupdf.Rect(x0, y0, x1, y1)
                # shrink a little so neighbouring visible glyphs survive
                dy = r.height * 0.3 if r.height > 3 else 0
                r = pymupdf.Rect(r.x0 + 0.3, r.y0 + dy, r.x1 - 0.3, r.y1 - dy)
                if r.is_empty or r.width <= 0:
                    continue
                doc[p].add_redact_annot(r, fill=False)
                redact_pages.add(p)
        elif loc.target == "pdf_annot" and loc.page is not None and loc.xref:
            annot_xrefs.setdefault(loc.page, set()).add(loc.xref)
        elif loc.target == "pdf_link" and loc.page is not None and loc.xref is not None:
            link_idx.setdefault(loc.page, set()).add(loc.xref)
        elif loc.target == "pdf_js":
            scrub_js = True
        elif loc.target == "pdf_embedded":
            scrub_emb = True
        elif loc.target == "pdf_meta":
            scrub_meta = True
    for p in sorted(redact_pages):
        doc[p].apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    for p, xrefs in annot_xrefs.items():
        page = doc[p]
        for a in list(page.annots() or []):
            if a.xref in xrefs:
                page.delete_annot(a)
        for w in list(page.widgets() or []):
            if w.xref in xrefs:
                page.delete_widget(w)
    for p, idxs in link_idx.items():
        page = doc[p]
        links = page.get_links()
        for i in sorted(idxs, reverse=True):
            if i < len(links):
                page.delete_link(links[i])
    if scrub_js or scrub_emb:
        doc.scrub(attached_files=scrub_emb, clean_pages=False, embedded_files=scrub_emb, hidden_text=False,
                  javascript=scrub_js, metadata=False, redactions=False, remove_links=False, reset_fields=False,
                  reset_responses=False, thumbnails=False, xml_metadata=False)
    if scrub_meta:
        doc.set_metadata({})
        try:
            doc.del_xml_metadata()
        except Exception:
            pass
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def clean_document(name: str, data: bytes, result: ScanResult, ids=None) -> dict:
    """Clean one document. Returns {'data': bytes, 'text': str, 'removed': n, 'filetype': ...}."""
    chosen = select(result, ids)
    if result.filetype == "pdf":
        cleaned_pdf = clean_pdf(data, chosen)
        rescan = scan_bytes(name, cleaned_pdf)
        return {"data": cleaned_pdf, "text": rescan.text_preview, "removed": len(chosen), "rescan": rescan}
    text, enc = decode_text(data)
    new_text = clean_text(text, chosen)
    out = _encode(new_text, enc if not enc.startswith("utf-16") and not enc.startswith("utf-32") else enc)
    if enc == "utf-8-sig":
        out = out if out.startswith(b"\xef\xbb\xbf") else b"\xef\xbb\xbf" + out
    rescan = scan_bytes(name, out)
    return {"data": out, "text": new_text, "removed": len(chosen), "rescan": rescan}


def _unique(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def default_export_dir(base: str = None) -> str:
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = base or os.path.join(os.path.expanduser("~"), "Documents", "PromptInjectionFinder_Export")
    return os.path.join(base, stamp)


def export(items, out_dir: str) -> dict:
    """items: list of dicts {name, data, result, ids}. Writes cleaned files and reports."""
    from .report import html_report

    os.makedirs(out_dir, exist_ok=True)
    clean_dir = os.path.join(out_dir, "bereinigt")
    os.makedirs(clean_dir, exist_ok=True)
    written = []
    summary = []
    for it in items:
        name, data, result = it["name"], it["data"], it["result"]
        cleaned = clean_document(name, data, result, it.get("ids"))
        target = _unique(os.path.join(clean_dir, os.path.basename(name)))
        with open(target, "wb") as fh:
            fh.write(cleaned["data"])
        written.append(target)
        if result.filetype == "pdf":
            txt_target = _unique(os.path.splitext(target)[0] + ".bereinigt.txt")
            with open(txt_target, "w", encoding="utf-8") as fh:
                fh.write(cleaned["text"])
            written.append(txt_target)
        rescan = cleaned["rescan"]
        summary.append({
            "file": name,
            "output": target,
            "before": result.to_dict(),
            "removed_findings": [f.id for f in select(result, it.get("ids"))],
            "after": {"risk_score": rescan.risk_score, "verdict": rescan.verdict,
                      "remaining_findings": [{"title": f.title, "score": f.score, "severity": f.severity}
                                             for f in rescan.findings]},
        })
    report_json = os.path.join(out_dir, "report.json")
    with open(report_json, "w", encoding="utf-8") as fh:
        json.dump({"generated": _dt.datetime.now().isoformat(timespec="seconds"), "files": summary}, fh,
                  ensure_ascii=False, indent=2)
    report_html = os.path.join(out_dir, "report.html")
    with open(report_html, "w", encoding="utf-8") as fh:
        fh.write(html_report(summary))
    written += [report_json, report_html]
    return {"out_dir": out_dir, "files": written, "summary": summary}
