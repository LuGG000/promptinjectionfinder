"""Command line interface.

    python -m pif gui                      # start the offline web interface
    python -m pif scan <files/dirs> [--json] [--min-score N]
    python -m pif clean <files/dirs> --out <dir> [--min-score N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .models import SEVERITIES

SEV_DE = {"critical": "KRITISCH", "high": "HOCH", "medium": "MITTEL", "low": "NIEDRIG", "info": "INFO"}
VERDICT_DE = {"dangerous": "GEFÄHRLICH", "suspicious": "VERDÄCHTIG", "clean": "UNAUFFÄLLIG"}


def _utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_scan(args) -> int:
    from .scanner import iter_files, scan_file

    worst = 0.0
    results = []
    for path in iter_files(args.paths):
        res = scan_file(path)
        worst = max(worst, res.risk_score)
        results.append(res)
        if args.json:
            continue
        print(f"\n== {path}  [{res.filetype}]  {VERDICT_DE[res.verdict]}  Risiko {res.risk_score:.0f}/100")
        if res.error:
            print(f"   Fehler: {res.error}")
        for f in res.findings:
            if f.score < args.min_score:
                continue
            where = f"Seite {f.location.page + 1}" if f.location.page is not None else (
                f"Zeile {f.location.line}" if f.location.line else "")
            print(f"  [{SEV_DE[f.severity]:>8} {f.score:5.1f}] {f.title}  ({where})")
            if args.verbose:
                print(f"           {f.description}")
                if f.evidence:
                    print("           Beleg: " + f.evidence[:300].replace("\n", " ⏎ "))
                if f.decoded:
                    print("           Dekodiert: " + f.decoded[:300].replace("\n", " ⏎ "))
    if args.json:
        print(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
    if not results:
        print("Keine unterstützten Dateien gefunden.", file=sys.stderr)
        return 2
    return 1 if worst >= args.fail_at else 0


def cmd_clean(args) -> int:
    from .cleaner import default_export_dir, export
    from .scanner import iter_files, scan_file

    items = []
    for path in iter_files(args.paths):
        res = scan_file(path)
        with open(path, "rb") as fh:
            data = fh.read()
        ids = [f.id for f in res.findings if f.removable and f.score >= args.min_score and
               (f.default_remove or args.all)]
        items.append({"name": os.path.basename(path), "data": data, "result": res, "ids": ids})
    if not items:
        print("Keine unterstützten Dateien gefunden.", file=sys.stderr)
        return 2
    out = args.out or default_export_dir()
    info = export(items, out)
    for s in info["summary"]:
        print(f"{s['file']}: Risiko {s['before']['risk_score']:.0f} -> {s['after']['risk_score']:.0f}  "
              f"({len(s['removed_findings'])} Funde entfernt)")
    print(f"\nExport: {info['out_dir']}")
    return 0


def cmd_gui(args) -> int:
    from .server import run

    run(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv=None) -> int:
    _utf8_console()
    p = argparse.ArgumentParser(prog="pif", description="PromptInjectionFinder – deterministischer Prompt-Injection-Scanner")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("scan", help="Dateien/Ordner scannen")
    s.add_argument("paths", nargs="+")
    s.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
    s.add_argument("--min-score", type=float, default=0.0)
    s.add_argument("--fail-at", type=float, default=65.0, help="Exit-Code 1 ab diesem Risiko (Standard 65)")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("clean", help="Dateien bereinigen und exportieren")
    c.add_argument("paths", nargs="+")
    c.add_argument("--out", help="Zielordner (Standard: Dokumente/PromptInjectionFinder_Export/<Zeit>)")
    c.add_argument("--min-score", type=float, default=0.0)
    c.add_argument("--all", action="store_true", help="auch Funde entfernen, die standardmäßig nicht entfernt werden")
    c.set_defaults(func=cmd_clean)

    g = sub.add_parser("gui", help="Weboberfläche starten (offline, localhost)")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--no-browser", action="store_true")
    g.set_defaults(func=cmd_gui)

    args = p.parse_args(argv)
    if not args.cmd:
        args = p.parse_args(["gui"] + (argv or []))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
