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
    with open(os.path.join(SAMPLES, "attack_recipe.md"), "rb") as fh:
        st, body, _ = call(base, "/api/upload?name=attack_recipe.md", raw=fh.read())
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
    assert (out / "cleaned" / "attack_recipe.md").exists()
    assert (out / "report.html").exists()


def test_pdf_page_render(base):
    with open(os.path.join(SAMPLES, "attack_cv.pdf"), "rb") as fh:
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
    with open(os.path.join(SAMPLES, "attack_meeting.txt"), "rb") as fh:
        res = json.loads(call(base, "/api/upload?name=attack_meeting.txt", raw=fh.read())[1])
    st, body, hdr = call(base, "/api/export_zip", {"items": [{"id": res["file_id"], "ids": None}]})
    assert st == 200 and hdr.get("Content-Type") == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(body)).namelist()
    assert "PromptInjectionFinder_Export/report.html" in names
    assert "PromptInjectionFinder_Export/cleaned/attack_meeting.txt" in names


def test_upload_batch_groups_files(base):
    for name in ("a.txt", "b.txt"):
        st, body, _ = call(base, f"/api/upload?name={name}&batch=grp123&batch_label=my%20folder", raw=b"hello world")
        assert st == 200
        b = json.loads(body)["batch"]
        assert b["id"] == "grp123" and b["kind"] == "upload" and b["label"] == "my folder"
    files = json.loads(call(base, "/api/files")[1])["results"]
    assert sum(1 for f in files if (f["batch"] or {}).get("id") == "grp123") == 2
    # ids are sanitised: anything odd gets a fresh one
    st, body, _ = call(base, "/api/upload?name=c.txt&batch=%3Cscript%3E", raw=b"x")
    assert re.fullmatch(r"[0-9a-f]{12}", json.loads(body)["batch"]["id"])


def test_scan_path_is_one_batch(base):
    st, body, _ = call(base, "/api/scan_path", {"path": SAMPLES})
    batches = {r["batch"]["id"] for r in json.loads(body)["results"]}
    kinds = {r["batch"]["kind"] for r in json.loads(body)["results"]}
    assert len(batches) == 1 and kinds == {"folder"}


def test_crawl_cancel_takes_effect_at_once():
    job = server.CrawlJob({"url": "https://example.com/"})  # not started: stands for a worker busy on a page
    job.results.append({"file_id": "x"})
    assert job.snapshot()["status"] == "running" and "results" not in job.snapshot()
    job.cancel()
    snap = job.snapshot()
    assert snap["status"] == "cancelled" and snap["results"] == [{"file_id": "x"}]
    assert job.batch["kind"] == "web" and job.batch["id"] == job.id
