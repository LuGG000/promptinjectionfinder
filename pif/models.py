"""Core data structures shared by all analyzers."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, asdict
from typing import Optional

from .i18n import LANGS, text

SEVERITIES = ["info", "low", "medium", "high", "critical"]

_ids = itertools.count(1)


def severity_for(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "low"
    return "info"


@dataclass
class Location:
    """Where a finding lives.

    For text-like files ``start``/``end`` are character offsets into the
    original (decoded) file content. For PDFs ``page`` is 0-based and
    ``rects`` holds the bounding boxes (x0, y0, x1, y1) of the affected glyphs.
    """
    start: Optional[int] = None
    end: Optional[int] = None
    line: Optional[int] = None
    page: Optional[int] = None
    rects: list = field(default_factory=list)  # [page, x0, y0, x1, y1]
    # Additional disjoint edits [start, end, replacement] for findings that
    # cover many scattered characters (e.g. zero-width chars sprinkled in words).
    ranges: list = field(default_factory=list)
    # PDF only: rects normalized to the rendered (rotated) page, [page, x0, y0, x1, y1] in 0..1
    view_rects: list = field(default_factory=list)
    xref: Optional[int] = None  # PDF object (annotation / embedded file) this finding refers to
    target: str = "text"  # text | pdf_text | pdf_annot | pdf_meta | pdf_js | pdf_embedded | pdf_link


@dataclass
class Finding:
    category: str
    rule: str
    title: object        # str or i18n.T (English + German)
    description: object  # str or i18n.T
    score: float
    evidence: str = ""
    decoded: str = ""
    location: Location = field(default_factory=Location)
    removable: bool = True
    default_remove: bool = True
    # How the cleaner should treat the span: "delete" removes it, "replace"
    # substitutes ``replacement``.
    action: str = "delete"
    replacement: str = ""
    tags: list = field(default_factory=list)
    # [start, end] of the individual rule matches (pattern findings only)
    hit_spans: list = field(default_factory=list)
    id: str = ""

    def __post_init__(self):
        self.score = float(max(0.0, min(100.0, self.score)))
        if not self.id:
            self.id = f"f{next(_ids)}"

    @property
    def severity(self) -> str:
        return severity_for(self.score)

    def to_dict(self, lang: str = "en") -> dict:
        """JSON-ready dict. ``title``/``description`` are in ``lang``; ``i18n`` holds both languages."""
        d = asdict(self)
        d["severity"] = self.severity
        d["title"] = text(self.title, lang)
        d["description"] = text(self.description, lang)
        d["i18n"] = {lg: {"title": text(self.title, lg), "description": text(self.description, lg)} for lg in LANGS}
        return d


@dataclass
class ScanResult:
    path: str
    name: str
    filetype: str
    findings: list = field(default_factory=list)
    text_preview: str = ""
    stats: dict = field(default_factory=dict)
    error: str = ""

    @property
    def risk_score(self) -> float:
        """Combine finding scores: probabilistic OR over the scores so that many
        medium signals add up, but a single critical one dominates."""
        best = {}
        for f in self.findings:
            best[f.rule] = max(best.get(f.rule, 0.0), f.score)
        scores = sorted(best.values(), reverse=True)
        if not scores:
            return 0.0
        top = scores[0]
        # Each further distinct kind of signal adds a damped share of the remaining headroom;
        # repetitions of the same rule do not add up.
        rest = 1.0
        for s in scores[1:]:
            if s >= 20:
                rest *= 1.0 - 0.35 * s / 100.0
        return round(top + (100.0 - top) * (1.0 - rest) * (top / 100.0), 1)

    @property
    def verdict(self) -> str:
        r = self.risk_score
        if r >= 65:
            return "dangerous"
        if r >= 20:
            return "suspicious"
        return "clean"

    def to_dict(self, lang: str = "en") -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "filetype": self.filetype,
            "risk_score": self.risk_score,
            "severity": severity_for(self.risk_score),
            "verdict": self.verdict,
            "findings": [f.to_dict(lang) for f in sorted(self.findings, key=lambda f: -f.score)],
            "text_preview": self.text_preview,
            "stats": self.stats,
            "error": self.error,
        }
