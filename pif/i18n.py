"""Bilingual user-facing text (English / German).

Findings are produced once and carry both languages, so the UI can switch
language without rescanning. ``T`` behaves enough like a string to be built
up with ``+``.
"""
from __future__ import annotations

import os

LANGS = ("en", "de")


def default_lang() -> str:
    lang = (os.environ.get("PIF_LANG") or "en").lower()[:2]
    return lang if lang in LANGS else "en"


class T:
    """A text in English and German."""

    __slots__ = ("en", "de")

    def __init__(self, en: str, de: str = None):
        self.en = en
        self.de = en if de is None else de

    def get(self, lang: str = "en") -> str:
        return self.de if lang == "de" else self.en

    def __add__(self, other):
        o = tr(other)
        return T(self.en + o.en, self.de + o.de)

    def __radd__(self, other):
        o = tr(other)
        return T(o.en + self.en, o.de + self.de)

    def __contains__(self, item) -> bool:
        return item in self.en or item in self.de

    def __eq__(self, other) -> bool:
        if isinstance(other, T):
            return self.en == other.en and self.de == other.de
        return other in (self.en, self.de)

    def __hash__(self):
        return hash((self.en, self.de))

    def __str__(self) -> str:
        return self.en

    def __repr__(self) -> str:
        return f"T({self.en!r}, {self.de!r})"

    def __len__(self) -> int:
        return len(self.en)

    def startswith(self, prefix) -> bool:
        return self.en.startswith(prefix) or self.de.startswith(prefix)

    def strip(self):
        return T(self.en.strip(), self.de.strip())

    def __deepcopy__(self, memo):
        return T(self.en, self.de)


def tr(x) -> T:
    """Coerce plain strings (identical in both languages) to T."""
    return x if isinstance(x, T) else T(str(x), str(x))


def text(x, lang: str = "en") -> str:
    return x.get(lang) if isinstance(x, T) else ("" if x is None else str(x))


def join(sep, items) -> T:
    items = [tr(i) for i in items]
    s = tr(sep)
    return T(s.en.join(i.en for i in items), s.de.join(i.de for i in items))
