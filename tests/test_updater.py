"""Update mechanism: archive download (simulated GitLab API) and git fast-forward."""
import http.server
import io
import json
import os
import shutil
import subprocess
import threading
import zipfile

import pytest

from pif import updater


def test_parse_version():
    assert updater.parse_version("v1.10.2") > updater.parse_version("1.9.9")
    assert updater.parse_version("v2.0") == (2, 0, 0)
    assert updater.parse_version("quatsch") == (0, 0, 0)


def _release_zip(version: str) -> bytes:
    buf = io.BytesIO()
    top = f"promptinjectionfinder-v{version}-abc123/"
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(top + "pif/__init__.py", f'__version__ = "{version}"\n')
        zf.writestr(top + "pif/neu.py", "X = 1\n")
        zf.writestr(top + "requirements.txt", "")
        zf.writestr(top + "run_linux_mac.sh", "#!/bin/sh\necho neu\n")
    return buf.getvalue()


@pytest.fixture()
def fake_gitlab():
    routes = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            for prefix, (ctype, body) in routes.items():
                if self.path.startswith(prefix):
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.end_headers()
                    self.wfile.write(body)
                    return
            self.send_response(404)
            self.end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/v4/projects/x", routes
    srv.shutdown()


def test_archive_update_replaces_program_keeps_venv(tmp_path, fake_gitlab, monkeypatch):
    api, routes = fake_gitlab
    routes["/api/v4/projects/x/repository/tags"] = ("application/json",
                                                    json.dumps([{"name": "v9.9.9"}, {"name": "v1.0.0"}]).encode())
    routes["/api/v4/projects/x/repository/archive.zip"] = ("application/zip", _release_zip("9.9.9"))
    root = tmp_path / "install"
    (root / "pif").mkdir(parents=True)
    (root / "pif" / "__init__.py").write_text('__version__ = "1.0.0"\n')
    (root / ".venv").mkdir()
    (root / ".venv" / "marker").write_text("bleibt")
    (root / "eigene_notizen.txt").write_text("bleibt auch")
    monkeypatch.setattr(updater, "API", api)
    monkeypatch.setattr(updater, "ROOT", str(root))
    monkeypatch.setattr(updater, "__version__", "1.0.0")
    monkeypatch.setattr(updater, "install_method", lambda: "archive")
    monkeypatch.setattr(updater, "_install_requirements", lambda log: None)

    info = updater.check()
    assert info["update_available"] and info["latest"] == "9.9.9"
    log = []
    res = updater.update(log=log.append)
    assert res["updated"]
    assert '"9.9.9"' in (root / "pif" / "__init__.py").read_text()
    assert (root / "pif" / "neu.py").exists()
    assert (root / ".venv" / "marker").read_text() == "bleibt"
    assert (root / "eigene_notizen.txt").exists()
    assert (root / ".update-backup" / "pif" / "__init__.py").exists()
    assert any("9.9.9" in line for line in log)


def test_already_up_to_date(fake_gitlab, monkeypatch):
    api, routes = fake_gitlab
    routes["/api/v4/projects/x/repository/tags"] = ("application/json", json.dumps([{"name": "v1.1.0"}]).encode())
    monkeypatch.setattr(updater, "API", api)
    monkeypatch.setattr(updater, "__version__", "1.1.0")
    monkeypatch.setattr(updater, "install_method", lambda: "archive")
    assert updater.update(log=lambda m: None)["updated"] is False


def test_private_project_message(fake_gitlab, monkeypatch):
    api, _routes = fake_gitlab  # no routes -> 404 like a private project
    monkeypatch.setattr(updater, "API", api)
    monkeypatch.setattr(updater, "install_method", lambda: "archive")
    with pytest.raises(updater.UpdateError, match="PIF_GITLAB_TOKEN"):
        updater.check()


@pytest.mark.skipif(not shutil.which("git"), reason="git nicht installiert")
def test_git_update_fast_forwards_to_release_tag(tmp_path, monkeypatch):
    def git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    origin = tmp_path / "origin"
    origin.mkdir()
    git("init", "-q", "-b", "main", cwd=origin)
    git("config", "user.email", "t@example.com", cwd=origin)
    git("config", "user.name", "Test", cwd=origin)
    (origin / "pif").mkdir()
    (origin / "pif" / "__init__.py").write_text('__version__ = "1.0.0"\n')
    git("add", ".", cwd=origin)
    git("commit", "-q", "-m", "v1", cwd=origin)
    git("tag", "v1.0.0", cwd=origin)
    clone = tmp_path / "clone"
    git("clone", "-q", str(origin), str(clone), cwd=tmp_path)
    (origin / "pif" / "__init__.py").write_text('__version__ = "1.2.0"\n')
    git("commit", "-q", "-am", "v1.2", cwd=origin)
    git("tag", "v1.2.0", cwd=origin)

    monkeypatch.setattr(updater, "ROOT", str(clone))
    monkeypatch.setattr(updater, "__version__", "1.0.0")
    monkeypatch.setattr(updater, "_install_requirements", lambda log: None)
    assert updater.install_method() == "git"
    assert updater.check()["latest"] == "1.2.0"
    assert updater.update(log=lambda m: None)["updated"]
    assert '"1.2.0"' in (clone / "pif" / "__init__.py").read_text()
