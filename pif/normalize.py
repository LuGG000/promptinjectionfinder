"""Build normalized "views" of a text that keep a mapping back to the original.

Attackers obfuscate instructions with homoglyphs, zero-width characters,
fancy Unicode letters, leetspeak or s p a c e d letters. Pattern matching runs
on a canonical skeleton of the text while every character of the skeleton
remembers the offset of the original character it came from, so findings can
be reported (and removed) at their exact original position.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .unicode_tools import fold_char, is_invisible, strip_accents

LEET = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
    "@": "a", "$": "s", "!": "i", "|": "l", "€": "e", "+": "t",
}

_SEP = r"[ .\-_*|·•/+~,:;'\"`]"
_SPACED_RUN = re.compile(
    r"(?<![a-z0-9])[a-z](?:" + _SEP + r"{1,3}[a-z](?![a-z0-9])){3,}"
)


@dataclass
class View:
    text: str
    index: list  # index[i] -> offset in original text of view char i

    def span(self, start: int, end: int) -> tuple:
        """Map a [start, end) range of the view back to the original text."""
        if start >= len(self.index):
            return (self.index[-1] + 1, self.index[-1] + 1) if self.index else (0, 0)
        s = self.index[start]
        e = self.index[max(start, end - 1)] + 1
        return s, e


def build_view(text: str, leet: bool = False) -> View:
    out_chars = []
    out_idx = []
    prev_space = True
    for i, ch in enumerate(text):
        cp = ord(ch)
        if is_invisible(cp):
            continue
        cat = unicodedata.category(ch)
        if cat in ("Mn", "Me"):  # combining marks (zalgo, accents) -> drop
            continue
        if ch.isspace():
            if not prev_space:
                out_chars.append(" ")
                out_idx.append(i)
                prev_space = True
            continue
        folded = strip_accents(fold_char(ch))
        for f in folded:
            if f.isspace():
                if not prev_space:
                    out_chars.append(" ")
                    out_idx.append(i)
                    prev_space = True
                continue
            out_chars.append(f)
            out_idx.append(i)
            prev_space = False

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

    s = "".join(out_chars)
    # Collapse s p a c e d   o u t letters ("i g n o r e") into words.
    if _SPACED_RUN.search(s):
        keep = [True] * len(s)
        for m in _SPACED_RUN.finditer(s):
            for k in range(m.start(), m.end()):
                if not s[k].isalpha():
                    keep[k] = False
        out_chars2 = []
        out_idx2 = []
        for k, c in enumerate(s):
            if keep[k]:
                out_chars2.append(c)
                out_idx2.append(out_idx[k])
        s = "".join(out_chars2)
        out_idx = out_idx2
    return View(s, out_idx)


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
        out_chars.append(ch.lower() if len(ch.lower()) == 1 else ch)
        out_idx.append(i)
        prev_space = False
    return View("".join(out_chars), out_idx)
