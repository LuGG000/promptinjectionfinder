"""Build normalized "views" of a text that keep a mapping back to the original.

Attackers obfuscate instructions with homoglyphs, zero-width characters,
fancy Unicode letters, leetspeak or s p a c e d letters. Pattern matching runs
on a canonical skeleton of the text while every character of the skeleton
remembers the offset of the original character it came from, so findings can
be reported (and removed) at their exact original position.

Regions where words were glued together by the normalization (spaced-out
letters, invisible characters inside words) are remembered as
``loose_regions``: only there the rule engine also accepts matches without
word separators ("ignoreallpreviousinstructions"), which keeps identifiers
like ``includeCredentials`` from matching.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .unicode_tools import fold_char, is_invisible, strip_accents

LEET = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
    "@": "a", "$": "s", "!": "i", "|": "l", "€": "e", "+": "t",
}

_SEP = r"[ .\-_*|·•/+~,:;'\"`]"
_SPACED_RUN = re.compile(
    r"(?<![a-z0-9])[a-z](?:" + _SEP + r"{1,3}[a-z](?![a-z0-9])){3,}"
)

# Per-character mapping cache: char -> folded string ("" = drop, " " = whitespace)
_MAP: dict = {}


def _map_char(ch: str) -> str:
    r = _MAP.get(ch)
    if r is None:
        cp = ord(ch)
        if is_invisible(cp) or unicodedata.category(ch) in ("Mn", "Me"):
            r = ""
        elif ch.isspace():
            r = " "
        else:
            r = "".join(" " if c.isspace() else c for c in strip_accents(fold_char(ch)))
        if len(_MAP) < 200_000:
            _MAP[ch] = r
    return r


@dataclass
class View:
    text: str
    index: list  # index[i] -> offset in original text of view char i
    loose_regions: list = field(default_factory=list)  # [(start, end)] in view coordinates
    changed: list = field(default_factory=list)  # leet view: positions that were translated

    def span(self, start: int, end: int) -> tuple:
        """Map a [start, end) range of the view back to the original text."""
        if start >= len(self.index):
            return (self.index[-1] + 1, self.index[-1] + 1) if self.index else (0, 0)
        s = self.index[start]
        e = self.index[max(start, end - 1)] + 1
        return s, e


def _merge(regions, pad=0, limit=None):
    out = []
    for s, e in sorted(regions):
        s = max(0, s - pad)
        e = e + pad if limit is None else min(limit, e + pad)
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [tuple(r) for r in out]


def build_view(text: str, leet: bool = False) -> View:
    out_chars = []
    out_idx = []
    loose = []
    prev_space = True
    dropped_inside = False
    for i, ch in enumerate(text):
        r = _map_char(ch)
        if not r:
            if not prev_space:
                dropped_inside = True
            continue
        for f in r:
            if f == " ":
                if not prev_space:
                    out_chars.append(" ")
                    out_idx.append(i)
                    prev_space = True
                dropped_inside = False
                continue
            if 0x1F100 <= ord(ch) <= 0x1F1FF:
                # enclosed / regional-indicator letters are written without spaces
                loose.append((len(out_chars), len(out_chars) + 1))
            if dropped_inside:
                # an invisible char sat between two visible chars: possible word split
                loose.append((len(out_chars) - 1, len(out_chars) + 1))
                dropped_inside = False
            out_chars.append(f)
            out_idx.append(i)
            prev_space = False

    changed = []
    if leet:
        n = len(out_chars)
        for k in range(n):
            c = out_chars[k]
            if c in LEET:
                left = out_chars[k - 1] if k > 0 else " "
                right = out_chars[k + 1] if k + 1 < n else " "
                # Only translate inside tokens that contain real letters.
                if left.isalpha() or right.isalpha():
                    out_chars[k] = LEET[c]
                    changed.append(k)

    s = "".join(out_chars)
    # Collapse s p a c e d   o u t letters ("i g n o r e") into words.
    if _SPACED_RUN.search(s):
        keep = [True] * len(s)
        runs = []
        for m in _SPACED_RUN.finditer(s):
            runs.append((m.start(), m.end()))
            for k in range(m.start(), m.end()):
                if not s[k].isalpha():
                    keep[k] = False
        newpos = []
        out_chars2 = []
        out_idx2 = []
        for k, c in enumerate(s):
            newpos.append(len(out_chars2))
            if keep[k]:
                out_chars2.append(c)
                out_idx2.append(out_idx[k])
        newpos.append(len(out_chars2))
        loose = [(newpos[a], newpos[min(b, len(s))]) for a, b in loose]
        loose += [(newpos[a], newpos[b]) for a, b in runs]
        changed = [newpos[k] for k in changed]
        s = "".join(out_chars2)
        out_idx = out_idx2
    return View(s, out_idx, _merge(loose, pad=0), changed)


def plain_view(text: str) -> View:
    """Lowercased text with whitespace collapsed, no folding (for raw patterns)."""
    out_chars = []
    out_idx = []
    prev_space = True
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                out_chars.append(" ")
                out_idx.append(i)
                prev_space = True
            continue
        lo = ch.lower()
        out_chars.append(lo if len(lo) == 1 else ch)
        out_idx.append(i)
        prev_space = False
    return View("".join(out_chars), out_idx)
