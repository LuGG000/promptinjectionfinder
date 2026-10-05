"""Optional JavaScript rendering through a locally installed Chromium browser.

Many pages build their visible content with JavaScript (tabs, generated
exercises, navigation). ``--dump-dom`` of a headless Chrome/Edge/Chromium/Brave
returns the DOM after the scripts ran. Nothing is installed or downloaded: if
no such browser exists, the static HTML is used.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

_CANDIDATES = {
    "win": [
        r"%ProgramW6432%\Google\Chrome\Application\chrome.exe",  # 64-bit dir, also from 32-bit Python
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramW6432%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramW6432%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%LocalAppData%\Chromium\Application\chrome.exe",
        r"%LocalAppData%\Vivaldi\Application\vivaldi.exe",
        r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe",
        r"%LocalAppData%\Programs\Opera\opera.exe",
        r"%ProgramFiles%\Opera\opera.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
        "/Applications/Opera.app/Contents/MacOS/Opera",
    ],
    "linux": [
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
        "microsoft-edge-stable", "brave-browser", "brave", "vivaldi", "vivaldi-stable", "opera",
        "/snap/bin/chromium", "/var/lib/flatpak/exports/bin/org.chromium.Chromium",
    ],
}

_found = None


def find_browser():
    """Path of a Chromium-based browser, or None."""
    global _found
    if _found is not None:
        return _found or None
    env = os.environ.get("PIF_BROWSER")
    cands = [env] if env else []
    key = "win" if sys.platform.startswith("win") else "darwin" if sys.platform == "darwin" else "linux"
    cands += _CANDIDATES[key]
    for c in cands:
        if not c:
            continue
        path = os.path.expanduser(os.path.expandvars(c))
        if "%" in path:
            continue  # variable not defined on this system
        if os.path.isfile(path):
            _found = path
            return path
        w = shutil.which(c)
        if w:
            _found = w
            return w
    _found = ""
    return None


_MODES = ["--headless=new", "--headless"]
_PROBE_TIMEOUT = 20  # a headless mode that has not worked yet gets a shorter chance when another one is left


def _run_order() -> list:
    return list(_MODES)


def _remember(mode: str, worked: bool) -> None:
    """Try the mode that worked first next time; a mode that hung goes last (some browsers hang in --headless=new)."""
    if worked:
        _MODES.remove(mode)
        _MODES.insert(0, mode)
    elif _MODES[0] == mode:
        _MODES.remove(mode)
        _MODES.append(mode)


def render_dom(url: str, budget_ms: int = 8000, timeout: int = 60):
    """Return the rendered HTML (str) of ``url`` or None if rendering is not possible."""
    browser = find_browser()
    if not browser:
        return None
    with tempfile.TemporaryDirectory(prefix="pif-render-") as profile:
        modes = _run_order()
        for n, headless in enumerate(modes):
            cmd = [browser, headless, "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                   "--disable-extensions", "--mute-audio", "--hide-scrollbars", f"--user-data-dir={profile}",
                   f"--virtual-time-budget={budget_ms}", "--dump-dom", url]
            if not sys.platform.startswith("win") and hasattr(os, "geteuid") and os.geteuid() == 0:
                cmd.insert(1, "--no-sandbox")  # Chromium refuses to run as root otherwise (containers)
            last = n == len(modes) - 1
            try:
                out = subprocess.run(cmd, capture_output=True, timeout=timeout if last else min(timeout, _PROBE_TIMEOUT))
            except subprocess.TimeoutExpired:
                _remember(headless, False)
                continue
            except OSError:
                continue
            html = out.stdout.decode("utf-8", "replace")
            if out.returncode == 0 and "<" in html[:2000]:
                _remember(headless, True)
                return html
    return None
