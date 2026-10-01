"""Offline web interface: a tiny HTTP server on localhost (standard library only).

Security: binds to 127.0.0.1, checks the Host header (DNS rebinding) and
requires a per-session token header on every API call, so other websites in
the browser cannot drive the local API.
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.parse
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .cleaner import clean_document, default_export_dir, export, select
from .scanner import SUPPORTED_EXT, iter_files, scan_bytes

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MAX_UPLOAD = 200 * 1024 * 1024


class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.files = {}  # id -> {"name", "path", "data", "result"}

    def add(self, name, data, path="", extra_css="", web=False, source=b""):
        if web:
            from .scanner import scan_web_page
            res = scan_web_page(name, data, path, extra_css, source)
        else:
            res = scan_bytes(name, data, path=path or name, extra_css=extra_css)
        fid = uuid.uuid4().hex[:12]
        with self.lock:
            self.files[fid] = {"name": name, "path": path or name, "data": data, "result": res,
                               "web": {"url": path, "css": extra_css} if web else None}
        return fid, res

    def get(self, fid):
        with self.lock:
            return self.files.get(fid)


STORE = Store()


class CrawlJob:
    """Background crawl + scan with progress reporting for the UI."""

    def __init__(self, opts: dict):
        self.id = uuid.uuid4().hex[:12]
        self.opts = opts
        self.status = "running"
        self.phase = "fetch"
        self.done = 0
        self.total = int(opts.get("max_pages") or 30)
        self.current = ""
        self.results = []
        self.log = []
        self.error = ""
        self.cancelled = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _progress(self, done, total, url):
        self.done, self.total, self.current = done, total, url

    def _run(self):
        from .crawler import Crawler
        try:
            o = self.opts
            crawler = Crawler(o.get("url", ""), max_depth=int(o.get("depth", 1)), max_pages=int(o.get("max_pages", 30)),
                              same_host=bool(o.get("same_host", True)), respect_robots=bool(o.get("robots", True)),
                              include_documents=bool(o.get("documents", True)),
                              discover_mentions=bool(o.get("discover", False)),
                              render_js=bool(o.get("render", False)),
                              progress=self._progress, cancel=lambda: self.cancelled)
            res = crawler.run()
            self.log = [{"url": e.url, "status": e.status, "note": e.note, "code": e.code} for e in res.log]
            self.phase = "analyze"
            self.total = len(res.pages)
            for i, page in enumerate(res.pages):
                if self.cancelled:
                    break
                self.done, self.current = i, page.url
                is_html = page.name.lower().endswith((".html", ".htm")) or "html" in page.content_type
                fid, r = STORE.add(page.name, page.rendered or page.data, path=page.url, extra_css=page.css,
                                   web=is_html, source=page.data if page.rendered else b"")
                self.results.append(_result_payload(fid, r))
            self.done = len(res.pages)
            self.status = "cancelled" if self.cancelled else "done"
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.status = "error"

    def snapshot(self) -> dict:
        d = {"status": self.status, "phase": self.phase, "done": self.done, "total": self.total,
             "current": self.current, "error": self.error, "log": self.log}
        if self.status != "running":
            d["results"] = self.results
        return d


JOBS = {}
TOKEN = secrets.token_urlsafe(24)


def _result_payload(fid, res) -> dict:
    d = res.to_dict()
    d["file_id"] = fid
    return d


class Handler(BaseHTTPRequestHandler):
    server_version = f"PromptInjectionFinder/{__version__}"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # ------------------------------------------------------------------ helpers
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _error(self, msg, code=400):
        self._json({"error": msg}, code)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ValueError("File too large (max. 200 MB)")
        return self.rfile.read(n) if n else b""

    def _authorized(self) -> bool:
        return self._host_ok() and secrets.compare_digest(self.headers.get("X-PIF-Token", ""), TOKEN)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        if not self._host_ok():
            return self._error("forbidden", 403)
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                with open(os.path.join(WEB_DIR, "index.html"), "r", encoding="utf-8") as fh:
                    page = fh.read().replace("__PIF_TOKEN__", TOKEN).replace("__PIF_VERSION__", __version__)
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if url.path.startswith("/static/"):
                name = os.path.basename(url.path[len("/static/"):])
                fp = os.path.join(WEB_DIR, name)
                if not os.path.isfile(fp):
                    return self._error("not found", 404)
                ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                with open(fp, "rb") as fh:
                    return self._send(200, fh.read(), ctype)
            if url.path == "/api/page":
                # images are loaded via <img>, so the token comes as query parameter
                if not secrets.compare_digest((q.get("t") or [""])[0], TOKEN):
                    return self._error("unauthorized", 401)
                return self._page_png(q)
            if not self._authorized():
                return self._error("unauthorized", 401)
            if url.path == "/api/info":
                from .render import find_browser
                browser = find_browser()
                return self._json({"version": __version__, "default_export_dir": default_export_dir(),
                                   "supported": sorted(SUPPORTED_EXT),
                                   "browser": os.path.basename(browser) if browser else None})
            if url.path == "/api/files":
                with STORE.lock:
                    items = [(fid, f["result"]) for fid, f in STORE.files.items()]
                return self._json({"results": [_result_payload(fid, r) for fid, r in items]})
            if url.path == "/api/update_check":
                from .updater import UpdateError, check
                try:
                    return self._json(check())
                except UpdateError as exc:
                    return self._json({"error": str(exc), "current": __version__}, 200)
            if url.path == "/api/crawl":
                job = JOBS.get((q.get("job") or [""])[0])
                if not job:
                    return self._error("Unknown job", 404)
                return self._json(job.snapshot())
            return self._error("not found", 404)
        except Exception as exc:
            traceback.print_exc()
            return self._error(f"{type(exc).__name__}: {exc}", 500)

    def _page_png(self, q):
        import pymupdf

        f = STORE.get((q.get("id") or [""])[0])
        if not f or f["result"].filetype != "pdf":
            return self._error("not found", 404)
        pno = int((q.get("page") or ["0"])[0])
        zoom = max(0.5, min(3.0, float((q.get("zoom") or ["1.5"])[0])))
        doc = pymupdf.open(stream=f["data"], filetype="pdf")
        if doc.needs_pass:
            doc.authenticate("")
        if not 0 <= pno < doc.page_count:
            return self._error("page out of range", 404)
        pix = doc[pno].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        png = pix.tobytes("png")
        doc.close()
        return self._send(200, png, "image/png")

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        if not self._authorized():
            return self._error("unauthorized", 401)
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/api/upload":
                name = (q.get("name") or ["upload.txt"])[0]
                data = self._body()
                fid, res = STORE.add(os.path.basename(name), data)
                return self._json(_result_payload(fid, res))
            payload = json.loads(self._body() or b"{}")
            if url.path == "/api/scan_path":
                path = os.path.expanduser(payload.get("path", "").strip().strip('"'))
                if not path or not os.path.exists(path):
                    return self._error("Path not found")
                out = []
                for fp in iter_files([path], recursive=bool(payload.get("recursive", True))):
                    with open(fp, "rb") as fh:
                        data = fh.read()
                    fid, res = STORE.add(os.path.basename(fp), data, path=fp)
                    out.append(_result_payload(fid, res))
                    if len(out) >= 2000:
                        break
                return self._json({"results": out})
            if url.path == "/api/preview":
                f = STORE.get(payload.get("id"))
                if not f:
                    return self._error("Unknown file", 404)
                cleaned = clean_document(f["name"], f["data"], f["result"], payload.get("ids"), web=f.get("web"), lang=payload.get("lang", "en"))
                rescan = cleaned["rescan"]
                return self._json({"text": cleaned["text"][:400_000], "removed": cleaned["removed"],
                                   "after": {"risk_score": rescan.risk_score, "verdict": rescan.verdict,
                                             "findings": [x.to_dict() for x in rescan.findings]}})
            if url.path == "/api/download":
                f = STORE.get(payload.get("id"))
                if not f:
                    return self._error("Unknown file", 404)
                cleaned = clean_document(f["name"], f["data"], f["result"], payload.get("ids"), web=f.get("web"), lang=payload.get("lang", "en"))
                body, fname = cleaned["data"], os.path.basename(f["name"])
                if "markdown" in cleaned:
                    body, fname = cleaned["markdown"].encode("utf-8"), os.path.splitext(fname)[0] + ".md"
                fn = urllib.parse.quote(fname)
                return self._send(200, body, "application/octet-stream",
                                  {"Content-Disposition": f"attachment; filename*=UTF-8''{fn}"})
            if url.path in ("/api/export", "/api/export_zip"):
                items = []
                for it in payload.get("items", []):
                    f = STORE.get(it.get("id"))
                    if f:
                        items.append({"name": f["name"], "data": f["data"], "result": f["result"], "ids": it.get("ids"),
                                      "web": f.get("web")})
                if not items:
                    return self._error("No files to export")
                if url.path == "/api/export_zip":
                    return self._send(200, _export_zip(items, payload.get("lang", "en")), "application/zip",
                                      {"Content-Disposition": 'attachment; filename="PromptInjectionFinder_Export.zip"'})
                out_dir = os.path.expanduser((payload.get("out_dir") or "").strip().strip('"')) or default_export_dir()
                info = export(items, out_dir, lang=payload.get("lang", "en"))
                return self._json({"out_dir": info["out_dir"], "files": info["files"],
                                   "summary": [{"file": s["file"], "before": s["before"]["risk_score"],
                                                "after": s["after"]["risk_score"],
                                                "removed": len(s["removed_findings"])} for s in info["summary"]]})
            if url.path == "/api/open_folder":
                path = payload.get("path", "")
                if os.path.isdir(path):
                    _open_folder(path)
                    return self._json({"ok": True})
                return self._error("Folder not found", 404)
            if url.path == "/api/crawl":
                job = CrawlJob(payload)
                JOBS[job.id] = job
                job.start()
                return self._json({"job": job.id})
            if url.path == "/api/update":
                from .updater import UpdateError, update
                log = []
                try:
                    info = update(force=bool(payload.get("force")), log=log.append)
                    return self._json({"ok": True, "updated": info.get("updated"), "log": log})
                except UpdateError as exc:
                    return self._json({"ok": False, "error": str(exc), "log": log})
            if url.path == "/api/crawl_cancel":
                job = JOBS.get(payload.get("job", ""))
                if job:
                    job.cancelled = True
                return self._json({"ok": True})
            if url.path == "/api/remove":
                with STORE.lock:
                    for fid in payload.get("ids", []):
                        STORE.files.pop(fid, None)
                return self._json({"ok": True})
            if url.path == "/api/clear":
                with STORE.lock:
                    STORE.files.clear()
                return self._json({"ok": True})
            return self._error("not found", 404)
        except Exception as exc:
            traceback.print_exc()
            return self._error(f"{type(exc).__name__}: {exc}", 500)


def _export_zip(items, lang: str = "en") -> bytes:
    """Export into a temporary folder and return it as ZIP (browser download, no path needed)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "PromptInjectionFinder_Export")
        export(items, root, lang=lang)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _dirs, files in os.walk(root):
                for fn in files:
                    full = os.path.join(dirpath, fn)
                    zf.write(full, os.path.relpath(full, tmp))
        return buf.getvalue()


def _open_folder(path: str) -> None:
    """Open a folder in the platform's file manager (no shell involved)."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
        return
    cmd = ["open", path] if sys.platform == "darwin" else ["xdg-open", path]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass  # no file manager available (e.g. headless server)


def _free_port(host, port):
    for p in range(port, port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    raise OSError("No free port found")


def make_server(host="127.0.0.1", port=8765):
    port = _free_port(host, port)
    return ThreadingHTTPServer((host, port), Handler)


def preload_paths(paths):
    n = 0
    for fp in iter_files(paths):
        with open(fp, "rb") as fh:
            STORE.add(os.path.basename(fp), fh.read(), path=fp)
        n += 1
    return n


def run(host="127.0.0.1", port=8765, open_browser=True, preload=None):
    if preload:
        print(f"{preload_paths(preload)} file(s) pre-scanned.")
    httpd = make_server(host, port)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"PromptInjectionFinder {__version__} is running offline at {url}")
    print("Keep this window open while using the tool. Quit with Ctrl+C.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
