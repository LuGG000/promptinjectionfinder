"""Standalone HTML report for exports (no external resources)."""
from __future__ import annotations

import datetime as _dt
import html

SEV_COLORS = {"critical": "#b3261e", "high": "#d9480f", "medium": "#b7791f", "low": "#2b6cb0", "info": "#6b7280"}
SEV_DE = {"critical": "Kritisch", "high": "Hoch", "medium": "Mittel", "low": "Niedrig", "info": "Info"}
VERDICT_DE = {"dangerous": "Gefährlich", "suspicious": "Verdächtig", "clean": "Unauffällig"}


def _e(s) -> str:
    return html.escape(str(s or ""))


def html_report(summary: list) -> str:
    rows = []
    for item in summary:
        b = item["before"]
        a = item["after"]
        removed = set(item["removed_findings"])
        frows = []
        for f in b["findings"]:
            sev = f["severity"]
            frows.append(
                f"<tr><td><span class='sev' style='background:{SEV_COLORS[sev]}'>{SEV_DE[sev]}</span></td>"
                f"<td><b>{_e(f['title'])}</b><div class='d'>{_e(f['description'])}</div>"
                + (f"<pre>{_e(f['evidence'][:1500])}</pre>" if f.get("evidence") else "")
                + (f"<div class='dl'>Dekodiert:</div><pre>{_e(f['decoded'][:1500])}</pre>" if f.get("decoded") else "")
                + f"</td><td>{_e(f['location'].get('line') or '')}</td>"
                f"<td>{'✔ entfernt' if f['id'] in removed else '–'}</td></tr>")
        rows.append(f"""
<section>
  <h2>{_e(item['file'])}</h2>
  <p>Vorher: <b>{VERDICT_DE[b['verdict']]}</b> (Risiko {b['risk_score']:.0f}/100) &nbsp;→&nbsp;
     Nachher: <b>{VERDICT_DE[a['verdict']]}</b> (Risiko {a['risk_score']:.0f}/100)</p>
  <p class='d'>Bereinigte Datei: {_e(item['output'])}</p>
  <table><thead><tr><th>Stufe</th><th>Fund</th><th>Zeile/Seite</th><th>Status</th></tr></thead>
  <tbody>{''.join(frows) or "<tr><td colspan=4>Keine Funde</td></tr>"}</tbody></table>
</section>""")
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prompt-Injection-Bericht</title>
<style>
body{{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:24px;background:#f6f7f9;color:#1f2328}}
h1{{margin-top:0}} section{{background:#fff;border:1px solid #d8dee4;border-radius:10px;padding:16px 20px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}} td,th{{text-align:left;vertical-align:top;padding:8px;border-top:1px solid #eaeef2}}
.sev{{color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;white-space:nowrap}}
.d{{color:#57606a}} .dl{{font-size:12px;color:#57606a;margin-top:6px}}
pre{{white-space:pre-wrap;word-break:break-word;background:#f6f8fa;border-radius:6px;padding:8px;margin:6px 0;font-size:12px}}
</style></head><body>
<h1>Prompt-Injection-Bericht</h1>
<p class="d">Erstellt: {_dt.datetime.now().strftime('%d.%m.%Y %H:%M')} · {len(summary)} Datei(en)</p>
{''.join(rows)}
</body></html>"""
