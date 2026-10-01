"""Standalone HTML report for exports (no external resources)."""
from __future__ import annotations

import datetime as _dt
import html

SEV_COLORS = {"critical": "#b3261e", "high": "#d9480f", "medium": "#b7791f", "low": "#2b6cb0", "info": "#6b7280"}
LABELS = {
    "en": {
        "sev": {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Info"},
        "verdict": {"dangerous": "Dangerous", "suspicious": "Suspicious", "clean": "Clean"},
        "title": "Prompt injection report", "created": "Created", "files": "file(s)", "before": "Before",
        "after": "After", "risk": "risk", "output": "Cleaned file", "level": "Level", "finding": "Finding",
        "where": "Line/page", "status": "Status", "removed": "✔ removed", "none": "No findings",
        "decoded": "Decoded:", "tasks": "tasks detected",
    },
    "de": {
        "sev": {"critical": "Kritisch", "high": "Hoch", "medium": "Mittel", "low": "Niedrig", "info": "Info"},
        "verdict": {"dangerous": "Gefährlich", "suspicious": "Verdächtig", "clean": "Unauffällig"},
        "title": "Prompt-Injection-Bericht", "created": "Erstellt", "files": "Datei(en)", "before": "Vorher",
        "after": "Nachher", "risk": "Risiko", "output": "Bereinigte Datei", "level": "Stufe", "finding": "Fund",
        "where": "Zeile/Seite", "status": "Status", "removed": "✔ entfernt", "none": "Keine Funde",
        "decoded": "Dekodiert:", "tasks": "Aufgaben erkannt",
    },
}


def _e(s) -> str:
    return html.escape(str(s or ""))


def html_report(summary: list, lang: str = "en") -> str:
    L = LABELS["de" if lang == "de" else "en"]
    rows = []
    for item in summary:
        b = item["before"]
        a = item["after"]
        removed = set(item["removed_findings"])
        frows = []
        for f in b["findings"]:
            sev = f["severity"]
            frows.append(
                f"<tr><td><span class='sev' style='background:{SEV_COLORS[sev]}'>{L['sev'][sev]}</span></td>"
                f"<td><b>{_e(f['title'])}</b><div class='d'>{_e(f['description'])}</div>"
                + (f"<pre>{_e(f['evidence'][:1500])}</pre>" if f.get("evidence") else "")
                + (f"<div class='dl'>{L['decoded']}</div><pre>{_e(f['decoded'][:1500])}</pre>" if f.get("decoded") else "")
                + f"</td><td>{_e(f['location'].get('line') or '')}</td>"
                f"<td>{L['removed'] if f['id'] in removed else '–'}</td></tr>")
        tasks = f" · {item['tasks']} {L['tasks']}" if item.get("tasks") else ""
        rows.append(f"""
<section>
  <h2>{_e(item['file'])}</h2>
  <p>{L['before']}: <b>{L['verdict'][b['verdict']]}</b> ({L['risk']} {b['risk_score']:.0f}/100) &nbsp;→&nbsp;
     {L['after']}: <b>{L['verdict'][a['verdict']]}</b> ({L['risk']} {a['risk_score']:.0f}/100){tasks}</p>
  <p class='d'>{L['output']}: {_e(item['output'])}</p>
  <table><thead><tr><th>{L['level']}</th><th>{L['finding']}</th><th>{L['where']}</th><th>{L['status']}</th></tr></thead>
  <tbody>{''.join(frows) or f"<tr><td colspan=4>{L['none']}</td></tr>"}</tbody></table>
</section>""")
    stamp = _dt.datetime.now().strftime("%d.%m.%Y %H:%M" if lang == "de" else "%Y-%m-%d %H:%M")
    return f"""<!doctype html><html lang="{'de' if lang == 'de' else 'en'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{L['title']}</title>
<style>
body{{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:24px;background:#f6f7f9;color:#1f2328}}
h1{{margin-top:0}} section{{background:#fff;border:1px solid #d8dee4;border-radius:10px;padding:16px 20px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}} td,th{{text-align:left;vertical-align:top;padding:8px;border-top:1px solid #eaeef2}}
.sev{{color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;white-space:nowrap}}
.d{{color:#57606a}} .dl{{font-size:12px;color:#57606a;margin-top:6px}}
pre{{white-space:pre-wrap;word-break:break-word;background:#f6f8fa;border-radius:6px;padding:8px;margin:6px 0;font-size:12px}}
</style></head><body>
<h1>{L['title']}</h1>
<p class="d">{L['created']}: {stamp} · {len(summary)} {L['files']}</p>
{''.join(rows)}
</body></html>"""
