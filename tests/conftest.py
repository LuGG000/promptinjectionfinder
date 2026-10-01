import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from pif.scanner import scan_bytes  # noqa: E402


def scan_text(text: str, name: str = "t.txt"):
    return scan_bytes(name, text.encode("utf-8"))


def rules_of(result):
    out = set()
    for f in result.findings:
        out.update(f.rule.split(","))
    return out
