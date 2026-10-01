"""Local web API: auth, upload, preview, download, export."""
import json
import os
import re
import threading
import urllib.error
import urllib.request

import pytest

from pif import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")


@pytest.fixture(scope="module")
def base():
    httpd = server.make_server(port=18765)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(base, path, data=None, raw=None, token=None, headers=None):
    h = {"X-PIF-Token": server.TOKEN if token is None else token}
    h.update(headers or {})
    body = None
    if raw is not None:
        body = raw
    elif data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=body, headers=h, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_index_contains_token(base):
    html = urllib.request.urlopen(base + "/").read().decode()
    assert re.search(r'name="pif-token" content="' + re.escape(server.TOKEN) + '"', html)
    assert urllib.request.urlopen(base + "/static/app.js").status == 200


def test_api_requires_token(base):
    assert call(base, "/api/info", token="wrong")[0] == 401
    assert call(base, "/api/upload?name=a.txt", raw=b"x", token="")[0] == 401


def test_dns_rebinding_blocked(base):
    assert call(base, "/", headers={"Host": "attacker.example"})[0] == 403


def test_full_flow(base, tmp_path):
    with open(os.path.join(SAMPLES, "angriff_rezept.md"), "rb") as fh:
        st, body, _ = call(base, "/api/upload?name=angriff_rezept.md", raw=fh.read())
    assert st == 200
    res = json.loads(body)
    assert res["verdict"] == "dangerous"
    ids = [f["id"] for f in res["findings"] if f["default_remove"]]

    st, body, _ = call(base, "/api/preview", {"id": res["file_id"], "ids": ids})
    prev = json.loads(body)
    assert st == 200 and prev["after"]["verdict"] == "clean"
    assert "Ignore all previous" not in prev["text"]

    st, body, hdr = call(base, "/api/download", {"id": res["file_id"], "ids": ids})
    assert st == 200 and b"Apfelkuchen" in body
    assert "attachment" in hdr.get("Content-Disposition", "")

    out = tmp_path / "export"
    st, body, _ = call(base, "/api/export", {"out_dir": str(out), "items": [{"id": res["file_id"], "ids": ids}]})
    assert st == 200
    assert (out / "bereinigt" / "angriff_rezept.md").exists()
    assert (out / "report.html").exists()


def test_pdf_page_render(base):
    with open(os.path.join(SAMPLES, "angriff_lebenslauf.pdf"), "rb") as fh:
        res = json.loads(call(base, "/api/upload?name=cv.pdf", raw=fh.read())[1])
    st, png, hdr = call(base, f"/api/page?id={res['file_id']}&page=0&t={server.TOKEN}")
    assert st == 200 and png[:4] == b"\x89PNG"
    assert call(base, f"/api/page?id={res['file_id']}&page=0&t=bad")[0] == 401


def test_scan_path(base):
    st, body, _ = call(base, "/api/scan_path", {"path": SAMPLES})
    assert st == 200 and len(json.loads(body)["results"]) >= 7
    assert call(base, "/api/scan_path", {"path": os.path.join(SAMPLES, "does-not-exist")})[0] == 400


def test_export_zip(base):
    import io
    import zipfile
    with open(os.path.join(SAMPLES, "angriff_meeting.txt"), "rb") as fh:
        res = json.loads(call(base, "/api/upload?name=angriff_meeting.txt", raw=fh.read())[1])
    st, body, hdr = call(base, "/api/export_zip", {"items": [{"id": res["file_id"], "ids": None}]})
    assert st == 200 and hdr.get("Content-Type") == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(body)).namelist()
    assert "PromptInjectionFinder_Export/report.html" in names
    assert "PromptInjectionFinder_Export/bereinigt/angriff_meeting.txt" in names
