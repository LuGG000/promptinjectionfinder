"""Update PromptInjectionFinder to the newest release (git tag vX.Y.Z on GitLab).

Two ways, chosen automatically:
  * installation is a git clone   -> ``git fetch --tags`` + fast-forward to the release tag
  * installation from a download  -> download the release archive and replace the program
                                     files; .venv, exports and own files stay untouched

For a private GitLab project set the environment variable PIF_GITLAB_TOKEN
(personal access token with read_api / read_repository scope).
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import __version__

PROJECT = os.environ.get("PIF_GITLAB_PROJECT", "LuGG000/promptinjectionfinder")
GITLAB = os.environ.get("PIF_GITLAB_URL", "https://gitlab.com").rstrip("/")
API = f"{GITLAB}/api/v4/projects/{urllib.parse.quote(PROJECT, safe='')}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# files/folders of the program that an archive update replaces
PROGRAM_ITEMS = ("pif", "tools", "tests", "samples", "README.md", "README.de.md", "LICENSE", "requirements.txt", "requirements-dev.txt",
                 "run_windows.bat", "run_linux_mac.sh", "run_mac.command", "update_windows.bat",
                 "update_linux_mac.sh", "install.sh", "install.ps1", ".gitlab-ci.yml", ".gitignore", ".gitattributes")


class UpdateError(Exception):
    pass


def parse_version(v: str) -> tuple:
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", v or "")
    if not m:
        return (0, 0, 0)
    return tuple(int(x or 0) for x in m.groups())


def _request(url: str, timeout: int = 30) -> bytes:
    headers = {"User-Agent": f"PromptInjectionFinder/{__version__} updater"}
    token = os.environ.get("PIF_GITLAB_TOKEN")
    if token:
        headers["PRIVATE-TOKEN"] = token
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise UpdateError(
                "The GitLab project is not publicly reachable. Either make the project public "
                "or set an access token in the environment variable PIF_GITLAB_TOKEN.") from None
        raise UpdateError(f"GitLab answered with HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise UpdateError(f"No connection to {GITLAB}: {e.reason}") from None


def _latest_via_git():
    """Newest vX.Y.Z tag of the clone's remote – uses git's own credentials (private repos work)."""
    r = subprocess.run(["git", "-C", ROOT, "ls-remote", "--tags", "origin"], capture_output=True, text=True,
                       timeout=60)
    if r.returncode != 0:
        return None
    tags = set(re.findall(r"refs/tags/(v\d+\.\d+(?:\.\d+)?)(?:\^\{\})?$", r.stdout, re.M))
    if not tags:
        raise UpdateError("There is no release (git tag vX.Y.Z) in the GitLab project yet.")
    tag = max(tags, key=parse_version)
    return {"version": tag.lstrip("v"), "tag": tag, "notes": ""}


def latest_release() -> dict:
    """{'version': '1.2.0', 'tag': 'v1.2.0', 'notes': '...'} of the newest release tag."""
    if install_method() == "git":
        found = _latest_via_git()
        if found:
            return found
    data = json.loads(_request(f"{API}/repository/tags?order_by=version&sort=desc&per_page=50"))
    tags = [t for t in data if re.fullmatch(r"v\d+\.\d+(\.\d+)?", t.get("name", ""))]
    if not tags:
        raise UpdateError("There is no release (git tag vX.Y.Z) yet.")
    tags.sort(key=lambda t: parse_version(t["name"]), reverse=True)
    t = tags[0]
    notes = ((t.get("release") or {}).get("description") or t.get("message") or "").strip()
    return {"version": t["name"].lstrip("v"), "tag": t["name"], "notes": notes}


def check() -> dict:
    rel = latest_release()
    return {"current": __version__, "latest": rel["version"], "tag": rel["tag"], "notes": rel["notes"],
            "update_available": parse_version(rel["version"]) > parse_version(__version__),
            "method": install_method()}


def install_method() -> str:
    if getattr(sys, "frozen", False):
        return "exe"
    if os.path.isdir(os.path.join(ROOT, ".git")) and shutil.which("git"):
        return "git"
    return "archive"


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise UpdateError(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout.strip()


def _update_git(tag: str, log) -> None:
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise UpdateError("The program folder has local changes. Please save or discard them first (git status).")
    log("Fetching releases from GitLab (git fetch) …")
    _git("fetch", "--tags", "--force", "origin")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":  # detached (e.g. a release checkout): just move to the new tag
        _git("-c", "advice.detachedHead=false", "checkout", "--quiet", tag)
    else:
        try:
            _git("merge", "--ff-only", "--quiet", tag)
        except UpdateError:
            raise UpdateError(f"The branch '{branch}' cannot be fast-forwarded to {tag} automatically "
                              f"(own commits?). Manually: git -C \"{ROOT}\" pull") from None
    log(f"Program files updated to {tag}.")


def _update_archive(tag: str, log) -> None:
    log(f"Downloading release {tag} …")
    raw = _request(f"{API}/repository/archive.zip?sha={urllib.parse.quote(tag)}", timeout=120)
    with tempfile.TemporaryDirectory(prefix="pif-update-") as tmp:
        zipfile.ZipFile(io.BytesIO(raw)).extractall(tmp)
        tops = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
        if len(tops) != 1 or not os.path.isdir(os.path.join(tmp, tops[0], "pif")):
            raise UpdateError("Unexpected content of the release archive.")
        src = os.path.join(tmp, tops[0])
        backup = os.path.join(ROOT, ".update-backup")
        shutil.rmtree(backup, ignore_errors=True)
        os.makedirs(backup)
        log("Replacing program files (backup in .update-backup) …")
        for item in PROGRAM_ITEMS:
            new, old = os.path.join(src, item), os.path.join(ROOT, item)
            if not os.path.exists(new):
                continue
            if os.path.exists(old):
                shutil.move(old, os.path.join(backup, item))
            if os.path.isdir(new):
                shutil.copytree(new, old)
            else:
                shutil.copy2(new, old)
            if item.endswith((".sh", ".command")):
                os.chmod(old, 0o755)
    log(f"Program files updated to {tag}.")


def _install_requirements(log) -> None:
    req = os.path.join(ROOT, "requirements.txt")
    if not os.path.isfile(req):
        return
    log("Updating dependencies (pip) …")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", req],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log("Warning: pip reported an error: " + (r.stderr or r.stdout).strip()[-400:])


def update(force: bool = False, log=print) -> dict:
    info = check()
    if info["method"] == "exe":
        raise UpdateError("The EXE version cannot replace itself. Please download the new version "
                          f"or build it from source: {GITLAB}/{PROJECT}/-/releases")
    if not info["update_available"] and not force:
        log(f"Already up to date (version {info['current']}).")
        return {**info, "updated": False}
    log(f"Update {info['current']} → {info['latest']} ({info['method']}) …")
    if info["method"] == "git":
        _update_git(info["tag"], log)
    else:
        _update_archive(info["tag"], log)
    _install_requirements(log)
    log("Done. Please restart PromptInjectionFinder.")
    return {**info, "updated": True}
