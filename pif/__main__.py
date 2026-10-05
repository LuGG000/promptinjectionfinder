"""Command line interface.

    python -m pif gui                      # start the offline web interface
    python -m pif scan <files/dirs> [--json] [--min-score N] [--lang de]
    python -m pif clean <files/dirs> --out <dir>
    python -m pif scan-url <url> [--depth N] [--out <dir>]
    python -m pif update [--check]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .i18n import default_lang, text

MSG = {
    "en": {
        "sev": {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW", "info": "INFO"},
        "verdict": {"dangerous": "DANGEROUS", "suspicious": "SUSPICIOUS", "clean": "CLEAN"},
        "risk": "risk", "error": "Error", "page": "page", "line": "line", "evidence": "Evidence", "decoded": "Decoded",
        "no_files": "No supported files found.", "removed": "findings removed", "no_page": "No page loaded.",
        "no_browser": "Note: no Chromium-based browser (Chrome, Edge, Chromium, Brave, Vivaldi, Opera) found – JavaScript is not executed, "
                      "so content created by scripts is missing. Install one of them (or set PIF_BROWSER) for complete scans.",
        "new_version": "New version available: {latest} (installed: {current}).", "update_with": "Update with:  pif update",
        "up_to_date": "Up to date: version {current} is the newest.", "update_failed": "Update not possible: {exc}",
        "close_window": "Press Enter to close this window ...",
    },
    "de": {
        "sev": {"critical": "KRITISCH", "high": "HOCH", "medium": "MITTEL", "low": "NIEDRIG", "info": "INFO"},
        "verdict": {"dangerous": "GEFÄHRLICH", "suspicious": "VERDÄCHTIG", "clean": "UNAUFFÄLLIG"},
        "risk": "Risiko", "error": "Fehler", "page": "Seite", "line": "Zeile", "evidence": "Beleg", "decoded": "Dekodiert",
        "no_files": "Keine unterstützten Dateien gefunden.", "removed": "Funde entfernt", "no_page": "Keine Seite geladen.",
        "no_browser": "Hinweis: kein Chromium-basierter Browser (Chrome, Edge, Chromium, Brave, Vivaldi, Opera) gefunden – JavaScript wird nicht "
                      "ausgeführt, Inhalte, die erst per Skript entstehen, fehlen. Für vollständige Scans einen davon installieren (oder PIF_BROWSER setzen).",
        "new_version": "Neue Version verfügbar: {latest} (installiert: {current}).", "update_with": "Aktualisieren mit:  pif update",
        "up_to_date": "Aktuell: Version {current} ist die neueste.", "update_failed": "Update nicht möglich: {exc}",
        "close_window": "Enter drücken, um dieses Fenster zu schließen ...",
    },
}


def _m(args) -> dict:
    return MSG["de" if getattr(args, "lang", "en") == "de" else "en"]


def _utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _print_finding(f, args, m, with_where=True):
    where = ""
    if with_where:
        where = (f"{m['page']} {f.location.page + 1}" if f.location.page is not None
                 else f"{m['line']} {f.location.line}" if f.location.line else "")
    print(f"  [{m['sev'][f.severity]:>10} {f.score:5.1f}] {text(f.title, args.lang)}" + (f"  ({where})" if where else ""))
    if args.verbose:
        print(f"             {text(f.description, args.lang)}")
        if f.evidence:
            print(f"             {m['evidence']}: " + f.evidence[:300].replace("\n", " ⏎ "))
        if f.decoded:
            print(f"             {m['decoded']}: " + f.decoded[:300].replace("\n", " ⏎ "))


def cmd_scan(args) -> int:
    from .scanner import iter_files, scan_file

    m = _m(args)
    worst = 0.0
    results = []
    for path in iter_files(args.paths):
        res = scan_file(path)
        worst = max(worst, res.risk_score)
        results.append(res)
        if args.json:
            continue
        print(f"\n== {path}  [{res.filetype}]  {m['verdict'][res.verdict]}  {m['risk']} {res.risk_score:.0f}/100")
        if res.error:
            print(f"   {m['error']}: {res.error}")
        for f in res.findings:
            if f.score >= args.min_score:
                _print_finding(f, args, m)
    if args.json:
        print(json.dumps([r.to_dict(args.lang) for r in results], ensure_ascii=False, indent=2))
    if not results:
        print(m["no_files"], file=sys.stderr)
        return 2
    return 1 if worst >= args.fail_at else 0


def cmd_clean(args) -> int:
    from .cleaner import default_export_dir, export
    from .scanner import iter_files, scan_file

    m = _m(args)
    items = []
    for path in iter_files(args.paths):
        res = scan_file(path)
        with open(path, "rb") as fh:
            data = fh.read()
        ids = [f.id for f in res.findings if f.removable and f.score >= args.min_score and
               (f.default_remove or args.all)]
        items.append({"name": os.path.basename(path), "data": data, "result": res, "ids": ids})
    if not items:
        print(m["no_files"], file=sys.stderr)
        return 2
    out = args.out or default_export_dir()
    info = export(items, out, lang=args.lang)
    for s in info["summary"]:
        print(f"{s['file']}: {m['risk']} {s['before']['risk_score']:.0f} -> {s['after']['risk_score']:.0f}  "
              f"({len(s['removed_findings'])} {m['removed']})")
    print(f"\nExport: {info['out_dir']}")
    return 0


def cmd_scan_url(args) -> int:
    from .cleaner import export
    from .crawler import Crawler
    from .render import find_browser
    from .scanner import scan_bytes, scan_web_page

    m = _m(args)

    def progress(done, total, url):
        print(f"  [{done + 1}/{total}] {url}", file=sys.stderr)

    render = (not args.no_render) and bool(find_browser())
    if not args.no_render and not render:
        print(m["no_browser"], file=sys.stderr)
    crawler = Crawler(args.url, max_depth=args.depth, max_pages=args.max_pages, same_host=not args.all_hosts,
                      same_path=not args.all_paths,
                      respect_robots=not args.ignore_robots, include_documents=not args.no_documents,
                      discover_mentions=args.discover, progress=progress, render_js=render)
    res = crawler.run()
    for e in res.log:
        if e.status != "loaded":
            code = f" {e.code}" if e.code else ""
            print(f"  {e.status}{code}: {e.url} {e.note}", file=sys.stderr)
    items, worst, out = [], 0.0, []
    for page in res.pages:
        is_html = page.name.lower().endswith((".html", ".htm")) or "html" in page.content_type
        data = page.rendered or page.data
        if is_html:
            r = scan_web_page(page.name, data, page.url, page.css, page.data if page.rendered else b"")
        else:
            r = scan_bytes(page.name, data, path=page.url)
        worst = max(worst, r.risk_score)
        out.append(r)
        items.append({"name": page.name, "data": data, "result": r, "ids": None,
                      "web": {"url": page.url, "css": page.css} if is_html else None})
        if not args.json:
            print(f"\n== {page.url}  [{r.filetype}]  {m['verdict'][r.verdict]}  {m['risk']} {r.risk_score:.0f}/100")
            for f in r.findings:
                if f.score >= args.min_score:
                    _print_finding(f, args, m, with_where=False)
    if args.json:
        print(json.dumps([r.to_dict(args.lang) for r in out], ensure_ascii=False, indent=2))
    if args.out and items:
        info = export(items, args.out, lang=args.lang)
        print(f"\nExport: {info['out_dir']}")
    if not res.pages:
        print(m["no_page"], file=sys.stderr)
        return 2
    return 1 if worst >= args.fail_at else 0


def cmd_update(args) -> int:
    from .updater import UpdateError, check, update

    m = _m(args)
    try:
        if args.check:
            info = check()
            if info["update_available"]:
                print(m["new_version"].format(**info))
                print(m["update_with"])
                return 10
            print(m["up_to_date"].format(**info))
            return 0
        update(force=args.force)
        return 0
    except UpdateError as exc:
        print(m["update_failed"].format(exc=exc), file=sys.stderr)
        return 3


def cmd_gui(args) -> int:
    from .server import run

    try:
        run(host=args.host, port=args.port, open_browser=not args.no_browser, preload=args.paths)
    except Exception:
        # run_windows.bat starts the server in a window of its own, which closes when python ends:
        # keep the error readable there
        if not os.environ.get("PIF_OWN_WINDOW"):
            raise
        import traceback
        traceback.print_exc()
        try:
            input("\n" + _m(args)["close_window"])
        except (EOFError, KeyboardInterrupt):
            pass
        return 1
    return 0


def main(argv=None) -> int:
    _utf8_console()
    # first start after an update: bring the launchers of an installer installation up to date
    from .updater import ensure_launchers_current
    ensure_launchers_current()
    # --lang works before and after the sub-command; the sub-command must not reset it
    lang_parent = argparse.ArgumentParser(add_help=False)
    lang_parent.add_argument("--lang", choices=("en", "de"), default=argparse.SUPPRESS,
                             help="language of findings and reports (default: en, or PIF_LANG)")

    p = argparse.ArgumentParser(prog="pif", description="PromptInjectionFinder – deterministic prompt injection scanner")
    p.add_argument("--lang", choices=("en", "de"), default=default_lang(),
                   help="language of findings and reports (default: en, or PIF_LANG)")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("scan", help="scan files/folders", parents=[lang_parent])
    s.add_argument("paths", nargs="+")
    s.add_argument("--json", action="store_true", help="print the result as JSON")
    s.add_argument("--min-score", type=float, default=0.0)
    s.add_argument("--fail-at", type=float, default=65.0, help="exit code 1 from this risk on (default 65)")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("clean", help="clean files and export them", parents=[lang_parent])
    c.add_argument("paths", nargs="+")
    c.add_argument("--out", help="target folder (default: Documents/PromptInjectionFinder_Export/<time>)")
    c.add_argument("--min-score", type=float, default=0.0)
    c.add_argument("--all", action="store_true", help="also remove findings that are not removed by default")
    c.set_defaults(func=cmd_clean)

    u = sub.add_parser("scan-url", help="load and scan a web page (and sub-pages)", parents=[lang_parent])
    u.add_argument("url")
    u.add_argument("--depth", type=int, default=1, help="link depth (0 = this page only, default 1)")
    u.add_argument("--max-pages", type=int, default=30)
    u.add_argument("--all-hosts", action="store_true", help="also follow links to other domains")
    u.add_argument("--all-paths", action="store_true",
                   help="also follow links outside the folder of the start page (default: stay below it)")
    u.add_argument("--ignore-robots", action="store_true", help="ignore robots.txt (only for your own sites)")
    u.add_argument("--no-documents", action="store_true", help="do not load linked PDF/TXT/MD files")
    u.add_argument("--discover", action="store_true", help="also try paths mentioned in text/comments")
    u.add_argument("--out", help="export cleaned text + tasks (Markdown) and a report to this folder")
    u.add_argument("--no-render", action="store_true", help="do not run JavaScript (delivered HTML only)")
    u.add_argument("--json", action="store_true")
    u.add_argument("--min-score", type=float, default=0.0)
    u.add_argument("--fail-at", type=float, default=65.0)
    u.add_argument("-v", "--verbose", action="store_true")
    u.set_defaults(func=cmd_scan_url)

    up = sub.add_parser("update", help="update to the newest release", parents=[lang_parent])
    up.add_argument("--check", action="store_true", help="only check whether a new version exists")
    up.add_argument("--force", action="store_true", help="reinstall even if already up to date")
    up.set_defaults(func=cmd_update)

    g = sub.add_parser("gui", help="start the web interface (offline, localhost)", parents=[lang_parent])
    g.add_argument("paths", nargs="*", help="optional: files/folders to scan right at start")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--no-browser", action="store_true")
    g.set_defaults(func=cmd_gui)

    args = p.parse_args(argv)
    if not args.cmd:
        args = p.parse_args(["gui"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
