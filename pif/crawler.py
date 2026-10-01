"""Fetch a web page and (optionally) its links / sub-pages for scanning.

Standard library only. Deliberately conservative:
  * only http(s); by default only the start host,
  * depth, page and size limits, small delay between requests,
  * honours robots.txt (can be switched off for one's own sites),
  * no JavaScript execution: what is analysed is the delivered HTML/CSS -
    which is also exactly what most LLM tools and scrapers see.

Linked stylesheets are fetched as well, because text hidden via an external
CSS class is otherwise invisible to the analysis.
"""
from __future__ import annotations

import hashlib
import html as _html
import posixpath
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field

from . import __version__

USER_AGENT = f"Mozilla/5.0 (compatible; PromptInjectionFinder/{__version__}; offline scanner)"
MAX_BYTES = 25 * 1024 * 1024
TIMEOUT = 20

DOC_EXT = {".pdf", ".md", ".markdown", ".txt", ".csv", ".json", ".xml", ".rst", ".tex", ".log", ".yaml", ".yml"}
HTML_TYPES = ("text/html", "application/xhtml+xml")
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".avif", ".mp4", ".webm", ".mp3", ".wav",
            ".ogg", ".zip", ".gz", ".tar", ".7z", ".rar", ".exe", ".msi", ".dmg", ".iso", ".woff", ".woff2", ".ttf",
            ".otf", ".eot", ".js", ".mjs", ".map", ".css", ".apk", ".deb", ".rpm"}

_TAG = re.compile(r"<(a|area|iframe|frame|link|embed|object|source)\b([^>]*)>", re.I)
_ATTR = re.compile(r"""([a-zA-Z:-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""")
_BASE = re.compile(r"<base\b[^>]*href\s*=\s*[\"']?([^\"'\s>]+)", re.I)
_MENTION = re.compile(r"(?<![\w@])((?:\.{0,2}/)?(?:[\w.-]+/)*[\w.-]+\.(?:html?|pdf|md|txt))(?![\w/])", re.I)


@dataclass
class Fetched:
    url: str
    name: str
    data: bytes
    content_type: str
    depth: int
    css: str = ""
    rendered: bytes = b""  # DOM after JavaScript (empty if not rendered)


@dataclass
class LogEntry:
    url: str
    status: str  # loaded | duplicate | skipped | error | http | limit | cancelled
    note: str = ""
    code: int = 0  # HTTP status for "http"


@dataclass
class CrawlResult:
    pages: list = field(default_factory=list)  # Fetched
    log: list = field(default_factory=list)    # LogEntry


def normalize_url(url: str, base: str = None):
    url = _html.unescape(url.strip())
    if base:
        url = urllib.parse.urljoin(base, url)
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    path = p.path or "/"
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), path, p.query, ""))


def _attrs(raw: str) -> dict:
    out = {}
    for m in _ATTR.finditer(raw):
        v = m.group(2)
        if v[0] in "\"'":
            v = v[1:-1]
        out[m.group(1).lower()] = v
    return out


def extract_links(page_html: str, base_url: str) -> tuple:
    """Return (links, stylesheets) found in an HTML document."""
    m = _BASE.search(page_html)
    base = urllib.parse.urljoin(base_url, m.group(1)) if m else base_url
    links, styles = [], []
    for m in _TAG.finditer(page_html):
        tag, a = m.group(1).lower(), _attrs(m.group(2))
        if tag == "link":
            rel = a.get("rel", "").lower()
            if "stylesheet" in rel and a.get("href"):
                styles.append(a["href"])
            elif rel in ("alternate", "next", "prev") and a.get("href"):
                links.append(a["href"])
            continue
        target = a.get("href") or a.get("src") or a.get("data")
        if target and not target.lower().startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
            links.append(target)
    norm = lambda xs: [u for u in (normalize_url(x, base) for x in xs) if u]
    styles_out = norm(styles)
    styles_out += [u for u in (normalize_url(x, base) for x in re.findall(r"@import\s+(?:url\()?['\"]?([^'\")\s;]+)", page_html))
                   if u]
    return list(dict.fromkeys(norm(links))), list(dict.fromkeys(styles_out))


def mentioned_paths(text: str, base_url: str) -> list:
    """File names / paths that appear in text or comments (e.g. 'vorlage.html')."""
    out = []
    for m in _MENTION.finditer(text):
        cand = m.group(1)
        if "://" in cand or cand.count(".") > 6:
            continue
        u = normalize_url(cand, base_url)
        if u:
            out.append(u)
    return list(dict.fromkeys(out))


def _disposition_filename(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"filename\*\s*=\s*(?:UTF-8'')?([^;]+)", value, re.I) or re.search(r'filename\s*=\s*"?([^";]+)"?', value, re.I)
    return posixpath.basename(urllib.parse.unquote(m.group(1).strip())) if m else ""


def name_for(url: str, content_type: str, disposition: str = "") -> str:
    p = urllib.parse.urlsplit(url)
    path = urllib.parse.unquote(p.path)
    fname = _disposition_filename(disposition)
    if not fname:  # signed download links often carry the name in the query string
        q = urllib.parse.parse_qs(p.query)
        fname = _disposition_filename(" ".join(q.get("response-content-disposition", [])))
    if fname:
        path = posixpath.join(posixpath.dirname(path.rstrip("/")) or "/", fname)
        p = p._replace(query="")
    if path.endswith("/") or not path:
        path += "index.html"
    ext = posixpath.splitext(path)[1].lower()
    if not ext or ext in (".php", ".asp", ".aspx", ".jsp", ".cgi"):
        if any(t in content_type for t in HTML_TYPES):
            path += ".html"
        elif "pdf" in content_type:
            path += ".pdf"
        elif "markdown" in content_type:
            path += ".md"
        elif content_type.startswith("text/"):
            path += ".txt"
    if p.query:
        stem, e = posixpath.splitext(path)
        path = f"{stem}_{re.sub(r'[^A-Za-z0-9]+', '_', p.query)[:40]}{e}"
    safe = "/".join(re.sub(r'[<>:"\\|?*\x00-\x1f]', "_", part) for part in path.split("/") if part not in ("", ".", ".."))
    return f"{p.netloc}/{safe}"


class Crawler:
    def __init__(self, start_url: str, max_depth: int = 1, max_pages: int = 30, same_host: bool = True,
                 respect_robots: bool = True, include_documents: bool = True, discover_mentions: bool = False,
                 delay: float = 0.25, progress=None, cancel=None, opener=None, render_js: bool = False):
        url = start_url.strip()
        if not re.match(r"https?://", url, re.I):
            url = "https://" + url
        self.start = normalize_url(url)
        if not self.start:
            raise ValueError("Invalid URL")
        self.host = urllib.parse.urlsplit(self.start).netloc
        self.max_depth = max(0, int(max_depth))
        self.max_pages = max(1, int(max_pages))
        self.same_host = same_host
        self.respect_robots = respect_robots
        self.include_documents = include_documents
        self.discover_mentions = discover_mentions
        self.delay = delay
        self.progress = progress or (lambda *a: None)
        self.cancel = cancel or (lambda: False)
        self.opener = opener or urllib.request.build_opener()
        self.render_js = render_js
        self._robots = {}
        self._css_cache = {}
        self._last = 0.0

    # ------------------------------------------------------------- helpers
    def _allowed_host(self, url: str) -> bool:
        return not self.same_host or urllib.parse.urlsplit(url).netloc == self.host

    def _robots_ok(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urllib.parse.urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots.get(key)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                status, _ct, data, _u = self._get(key + "/robots.txt", limit=512 * 1024)
                rp.parse(data.decode("utf-8", "replace").splitlines() if status == 200 else [])
            except Exception:
                rp.parse([])
            self._robots[key] = rp
        return rp.can_fetch(USER_AGENT, url)

    def _get(self, url: str, limit: int = MAX_BYTES):
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*",
                                                   "Accept-Language": "de,en;q=0.8"})
        self.last_disposition = ""
        try:
            with self.opener.open(req, timeout=TIMEOUT) as r:
                data = r.read(limit + 1)
                status, ctype, final = r.status, (r.headers.get("Content-Type") or "").lower(), r.geturl()
                self.last_disposition = r.headers.get("Content-Disposition") or ""
        except urllib.error.HTTPError as e:
            status, ctype, final, data = e.code, (e.headers.get("Content-Type") or "").lower(), url, b""
        finally:
            self._last = time.monotonic()
        if len(data) > limit:
            raise ValueError(f"larger than {limit // (1024 * 1024)} MB")
        return status, ctype, data, final

    def _css_for(self, urls) -> str:
        out = []
        for u in urls[:15]:
            if u not in self._css_cache:
                css = ""
                try:
                    if self._robots_ok(u):
                        status, _ct, data, _f = self._get(u, limit=3 * 1024 * 1024)
                        if status == 200:
                            css = data.decode("utf-8", "replace")
                except Exception:
                    css = ""
                self._css_cache[u] = css
            out.append(self._css_cache[u])
        return "\n".join(out)

    # ------------------------------------------------------------- crawl
    def run(self) -> CrawlResult:
        result = CrawlResult()
        queue = [(self.start, 0, "start")]
        seen = {self.start}
        digests = {}
        while queue and len(result.pages) < self.max_pages:
            if self.cancel():
                result.log.append(LogEntry("", "cancelled"))
                break
            url, depth, origin = queue.pop(0)
            self.progress(len(result.pages), self.max_pages, url)
            if not self._robots_ok(url):
                result.log.append(LogEntry(url, "skipped", "blocked by robots.txt"))
                continue
            try:
                status, ctype, data, final = self._get(url)
            except Exception as exc:
                result.log.append(LogEntry(url, "error", str(exc)[:200]))
                continue
            if status != 200:
                result.log.append(LogEntry(url, "http", origin, code=status))
                continue
            final = normalize_url(final) or url
            is_html = any(t in ctype for t in HTML_TYPES) or (not ctype and data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")))
            ext = posixpath.splitext(urllib.parse.urlsplit(final).path)[1].lower()
            is_doc = ("pdf" in ctype or ext in DOC_EXT or ctype.startswith("text/plain") or "markdown" in ctype)
            if not (is_html or is_doc):
                result.log.append(LogEntry(url, "skipped", f"not a text document ({ctype or 'unknown'})"))
                continue
            digest = hashlib.sha1(data).hexdigest()
            if digest in digests:
                result.log.append(LogEntry(final, "duplicate", f"same content as {digests[digest]}"))
                continue
            digests[digest] = final
            page = Fetched(final, name_for(final, ctype, self.last_disposition), data, ctype, depth)
            result.pages.append(page)
            result.log.append(LogEntry(final, "loaded", f"{len(data) // 1024} KB · depth {depth} · {origin}"))
            if not is_html:
                continue
            text = data.decode(_charset(ctype, data), "replace")
            if self.render_js:
                from .render import render_dom
                self.progress(len(result.pages) - 1, self.max_pages, "rendering " + final)
                dom = render_dom(final)
                if dom:
                    page.rendered = dom.encode("utf-8")
                    text = text + "\n" + dom  # links that only exist after JavaScript
            links, styles = extract_links(text, final)
            page.css = self._css_for(styles)
            if depth >= self.max_depth:
                continue
            candidates = [(u, "link") for u in links]
            if self.discover_mentions:
                candidates += [(u, "mentioned in text") for u in mentioned_paths(text, final)]
            for u, why in candidates:
                if u in seen or not self._allowed_host(u):
                    continue
                uext = posixpath.splitext(urllib.parse.urlsplit(u).path)[1].lower()
                if uext in SKIP_EXT or (uext in DOC_EXT and not self.include_documents):
                    continue
                seen.add(u)
                queue.append((u, depth + 1, f"{why} from {final}"))
        if queue and len(result.pages) >= self.max_pages:
            result.log.append(LogEntry("", "limit", f"page limit {self.max_pages} reached, {len(queue)} more links not loaded"))
        return result


def _charset(ctype: str, data: bytes) -> str:
    m = re.search(r"charset=([\w-]+)", ctype)
    if not m:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", data[:4096], re.I)
        enc = m.group(1).decode("ascii", "replace") if m else "utf-8"
    else:
        enc = m.group(1)
    try:
        "".encode(enc)
        return enc
    except LookupError:
        return "utf-8"
