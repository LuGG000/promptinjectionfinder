"""Format-independent analysis of decoded text.

Detects
  * injection phrases (multilingual rule base on normalized text views),
  * Unicode smuggling: tag characters, variation-selector ("emoji") payloads,
    zero-width steganography, bidi overrides, homoglyphs, styled letters,
  * encoded payloads: Base64, hex, URL/HTML-entity encoding, binary, ROT13,
    reversed text,
  * terminal tricks (ANSI conceal, carriage-return overwrite) and layout
    tricks (text pushed far to the right or below many blank lines).
"""
from __future__ import annotations

import base64
import binascii
import codecs
import html
import re
import unicodedata
import urllib.parse

from .i18n import T, join
from .models import Finding, Location
from .patterns import CATEGORY_TITLES, combine, find_hits, payload_score, transformed_hits
from . import unicode_tools as U

CATEGORY_DESCRIPTIONS = {
    "override": T("Tries to override previous/system instructions of an AI model.",
                  "Versucht, vorherige/System-Anweisungen eines KI-Modells außer Kraft zu setzen."),
    "role": T("Tries to force a new role or mode onto the AI model.",
              "Versucht, dem KI-Modell eine neue Rolle oder einen Modus aufzuzwingen."),
    "prompt_leak": T("Asks the model to reveal its system prompt or internal instructions.",
                     "Fordert das Modell auf, seinen Systemprompt oder interne Anweisungen preiszugeben."),
    "delimiter": T("Contains fake chat/role markers to impersonate a system or assistant message.",
                   "Enthält gefälschte Chat-/Rollenmarker, um eine System- oder Assistenten-Nachricht vorzutäuschen."),
    "ai_address": T("Addresses an AI system directly – typical for hidden instructions in documents.",
                    "Spricht ein KI-System direkt an – typisch für versteckte Anweisungen in Dokumenten."),
    "conceal": T("Asks to hide actions from the human.", "Fordert, Aktionen vor dem Menschen zu verbergen."),
    "exfil": T("Tries to send data to external targets or to obtain secrets.",
               "Versucht, Daten an externe Ziele zu senden oder Geheimnisse abzugreifen."),
    "tool": T("Tries to trigger commands or tool calls.", "Versucht, Befehle oder Werkzeugaufrufe auszulösen."),
    "jailbreak": T("Typical jailbreak wording to defeat safety measures.",
                   "Typische Jailbreak-Formulierung zum Aushebeln von Schutzmaßnahmen."),
    "manipulation": T("Tries to manipulate ratings, classifications or outputs.",
                      "Versucht, Bewertungen, Klassifikationen oder Ausgaben zu manipulieren."),
}

_TERMINATORS = ".!?\n。！？"


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def visible_repr(s: str, limit: int = 400) -> str:
    """Make invisible characters visible for evidence display."""
    out = []
    for ch in s[:limit]:
        cp = ord(ch)
        if ch in "\n\t":
            out.append(ch)
        elif U.is_invisible(cp) or U.is_private_use(cp) or cp == 0x1B:
            out.append(f"⟦U+{cp:04X}⟧")
        else:
            out.append(ch)
    if len(s) > limit:
        out.append(" …")
    return "".join(out)


def context(text: str, start: int, end: int, pad: int = 60) -> str:
    s = max(0, start - pad)
    e = min(len(text), end + pad)
    return ("…" if s > 0 else "") + visible_repr(text[s:e], 600) + ("…" if e < len(text) else "")


def expand_to_sentence(text: str, start: int, end: int, limit: int = 400) -> tuple:
    s = start
    lo = max(0, start - limit)
    while s > lo and text[s - 1] not in _TERMINATORS:
        if text[s - 1] in " \t" and text[max(0, s - 4):s].strip(" \t") == "" and s - 4 >= 0:
            break  # a wide gap of whitespace separates unrelated content
        s -= 1
    if s == lo and lo > 0:
        s = start
    while s < start and text[s].isspace():
        s += 1
    e = end
    hi = min(len(text), end + limit)
    while e < hi and text[e] not in _TERMINATORS:
        e += 1
    if e < len(text) and text[e] in ".!?。！？":
        e += 1
    if e == hi and hi < len(text):
        e = end
    return s, e


def _payload_note(hits):
    if not hits:
        return ""
    cats = sorted({h.rule.category for h in hits})
    names = join(", ", [CATEGORY_TITLES[c] for c in cats])
    return T(" The hidden content contains injection patterns: ", " Der verborgene Inhalt enthält Injection-Muster: ") \
        + names + "."


# ---------------------------------------------------------------------------
# Injection phrases
# ---------------------------------------------------------------------------

def pattern_findings(text: str, hidden_context: bool = False, min_score: float = 20) -> list:
    hits = find_hits(text)
    if not hits:
        return []
    clusters = []
    cur = [hits[0]]
    cur_end = hits[0].end
    for h in hits[1:]:
        gap = text[cur_end:h.start] if h.start > cur_end else ""
        if h.start - cur_end <= 160 and "\n\n" not in gap:
            cur.append(h)
            cur_end = max(cur_end, h.end)
        else:
            clusters.append(cur)
            cur = [h]
            cur_end = h.end
    clusters.append(cur)

    findings = []
    for cl in clusters:
        best = {}
        for h in cl:
            best[h.rule.id] = max(best.get(h.rule.id, 0), h.rule.weight)
        score = combine(best.values())
        cats = []
        for h in sorted(cl, key=lambda h: -h.rule.weight):
            if h.rule.category not in cats:
                cats.append(h.rule.category)
        if len(cats) >= 3:
            score += 8
        if hidden_context:
            score += 20
        score = min(100.0, score)
        if score < min_score:
            continue
        start = min(h.start for h in cl)
        end = max(h.end for h in cl)
        s, e = expand_to_sentence(text, start, end)
        title = CATEGORY_TITLES[cats[0]]
        desc = CATEGORY_DESCRIPTIONS[cats[0]]
        if len(cats) > 1:
            desc += T(" Further signals: ", " Weitere Signale: ") + join(", ", [CATEGORY_TITLES[c] for c in cats[1:]]) + "."
        matched = "; ".join(sorted({f"“{h.matched.strip()[:60]}”" for h in cl}))
        desc += T(" Matches: ", " Treffer: ") + matched
        findings.append(Finding(
            category="injection",
            rule=",".join(sorted(best)),
            title="Prompt injection: " + title,
            description=desc,
            score=score,
            evidence=visible_repr(text[s:e]),
            location=Location(start=s, end=e, line=line_of(text, s)),
            default_remove=score >= 40,
            tags=cats,
            hit_spans=[[h.start, h.end] for h in cl],
        ))
    return findings


# ---------------------------------------------------------------------------
# Unicode smuggling
# ---------------------------------------------------------------------------

def _runs(text: str, pred) -> list:
    runs = []
    i = 0
    n = len(text)
    while i < n:
        if pred(ord(text[i])):
            j = i
            while j < n and pred(ord(text[j])):
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def _prev_visible(text: str, i: int) -> str:
    j = i - 1
    while j >= 0 and (U.is_variation_selector(ord(text[j])) or 0x1F3FB <= ord(text[j]) <= 0x1F3FF):
        j -= 1
    return text[j] if j >= 0 else ""


def _has_rtl(text: str) -> bool:
    for ch in text:
        if unicodedata.bidirectional(ch) in ("R", "AL"):
            return True
    return False


def _complex_script(ch: str) -> bool:
    sc = U.script_of(ch)
    return bool(sc) and sc not in ("LATIN",)


def unicode_findings(text: str) -> list:
    if text.isascii():  # fast path: none of the Unicode tricks can be present
        return _control_findings(text) + _terminal_findings(text)
    findings = []

    # --- Tag characters (ASCII smuggling) ---------------------------------
    for s, e in _runs(text, U.is_tag):
        run = text[s:e]
        decoded = U.decode_tags(run)
        if s > 0 and text[s - 1] == "\U0001F3F4" and re.fullmatch(r"[a-z0-9]{2,7}", decoded) and run.endswith("\U000E007F"):
            continue  # legitimate subdivision flag like England / Scotland
        ps, hits = payload_score(decoded)
        score = max(72.0, min(100.0, ps + 20)) if decoded.strip() else 45.0
        findings.append(Finding(
            category="unicode",
            rule="unicode.tags",
            title=T("ASCII smuggling via invisible Unicode tag characters",
                    "ASCII-Smuggling über unsichtbare Unicode-Tag-Zeichen"),
            description=T(f"{e - s} invisible tag characters (U+E0000–E007F) encode hidden ASCII text that humans "
                          "cannot see but AI models read.",
                          f"{e - s} unsichtbare Tag-Zeichen (U+E0000–E007F) kodieren versteckten ASCII-Text, "
                          "den Menschen nicht sehen, KI-Modelle aber lesen.") + _payload_note(hits),
            score=score,
            evidence=context(text, s, e),
            decoded=decoded,
            location=Location(start=s, end=e, line=line_of(text, s)),
            tags=["hidden"],
        ))

    # --- Variation selector smuggling ("text in emoji") -------------------
    for s, e in _runs(text, U.is_variation_selector):
        length = e - s
        base = _prev_visible(text, s)
        if length == 1:
            continue  # single selectors are normal (emoji presentation, CJK IVS)
        decoded = U.decode_variation_selectors(text[s:e])
        ps, hits = payload_score(decoded)
        readable = U.printable_ratio(decoded) > 0.8 and len(decoded.strip()) >= 2
        if readable:
            score = max(72.0, min(100.0, ps + 20))
            title = T("Hidden message in an emoji (variation selector smuggling)",
                      "Versteckte Nachricht in Emoji (Variation-Selector-Smuggling)")
            desc = T(f"{length} invisible variation selectors are attached to “{base}”. "
                     "Each selector encodes one byte – together they form hidden text.",
                     f"An das Zeichen „{base}“ sind {length} unsichtbare Variation Selectors angehängt. "
                     "Jeder Selector kodiert ein Byte – zusammen ergeben sie versteckten Text.") + _payload_note(hits)
        else:
            score = 40.0
            title = T("Unusual run of variation selectors", "Ungewöhnliche Häufung von Variation Selectors")
            desc = T(f"{length} consecutive variation selectors after “{base}” – possible hidden data channel.",
                     f"{length} aufeinanderfolgende Variation Selectors nach „{base}“ – möglicher versteckter Datenkanal.")
        rs = s
        if text[s] in "︎️" and base and U.is_emoji_like(ord(base)):
            rs = s + 1  # keep the normal emoji presentation selector
        findings.append(Finding(
            category="unicode",
            rule="unicode.variation_selectors",
            title=title,
            description=desc,
            score=score,
            evidence=context(text, s, e),
            decoded=decoded if readable else "",
            location=Location(start=rs, end=e, line=line_of(text, s)),
            tags=["hidden", "emoji"],
        ))

    # --- Zero-width / invisible formatting characters ---------------------
    def zw_pred(cp):
        if U.is_tag(cp) or U.is_variation_selector(cp) or cp in U.BIDI_CONTROLS:
            return False
        if cp in U.ZERO_WIDTH:
            return True
        return unicodedata.category(chr(cp)) == "Cf"

    suspicious = []
    soft = []
    n = len(text)
    for i, ch in enumerate(text):
        cp = ord(ch)
        if not zw_pred(cp):
            continue
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < n else ""
        j = i + 1
        while j < n and zw_pred(ord(text[j])):
            j += 1
        nxt_vis = text[j] if j < n else ""
        if cp == 0xFEFF and i == 0:
            continue
        if cp == 0x200D and prev and nxt and (U.is_emoji_like(ord(_prev_visible(text, i) or " ")) or 0x1F3FB <= ord(prev) <= 0x1F3FF) and U.is_emoji_like(ord(nxt)):
            continue  # emoji ZWJ sequence
        if cp in (0x200C, 0x200D) and (_complex_script(_prev_visible(text, i)) or _complex_script(nxt_vis)):
            continue  # required joiner in Arabic/Indic/Persian scripts
        if cp == 0x00AD:
            soft.append(i)
            continue
        if cp == 0x2800 and (0x2800 <= ord(prev or " ") <= 0x28FF or 0x2800 <= ord(nxt or " ") <= 0x28FF):
            continue  # blank cell inside braille graphics
        suspicious.append(i)

    if suspicious:
        # group into runs
        runs = []
        for i in suspicious:
            if runs and runs[-1][1] == i:
                runs[-1][1] = i + 1
            else:
                runs.append([i, i + 1])
        used = set()
        for s, e in runs:
            if e - s >= 8:
                decoded = U.decode_zero_width_binary(text[s:e])
                if decoded:
                    ps, hits = payload_score(decoded)
                    findings.append(Finding(
                        category="unicode",
                        rule="unicode.zw_stego",
                        title=T("Zero-width steganography (hidden binary message)",
                                "Zero-Width-Steganografie (versteckte Binärnachricht)"),
                        description=T(f"{e - s} invisible characters encode a hidden message as a bit sequence.",
                                      f"{e - s} unsichtbare Zeichen kodieren als Bitfolge eine versteckte Nachricht.")
                        + _payload_note(hits),
                        score=max(75.0, min(100.0, ps + 20)),
                        evidence=context(text, s, e),
                        decoded=decoded,
                        location=Location(start=s, end=e, line=line_of(text, s)),
                        tags=["hidden"],
                    ))
                    used.add((s, e))
        rest = [r for r in runs if (r[0], r[1]) not in used]
        if rest:
            count = sum(e - s for s, e in rest)
            splits = sum(1 for s, e in rest if s > 0 and e < n and text[s - 1].isalnum() and text[e].isalnum())
            score = 15.0 if count <= 2 else 32.0 if count <= 10 else 48.0
            if splits:
                score += 15
            names = sorted({U.char_name(ord(text[s])) for s, _ in rest})
            desc = T(f"{count} invisible characters found ({', '.join(names[:5])}). ",
                     f"{count} unsichtbare Zeichen gefunden ({', '.join(names[:5])}). ")
            if splits:
                desc += T(f"{splits}× a word is split – a typical technique to evade filters.",
                          f"{splits}× wird ein Wort zerteilt – typische Technik, um Filter zu umgehen.")
            s0 = rest[0][0]
            findings.append(Finding(
                category="unicode",
                rule="unicode.zero_width",
                title=T("Invisible zero-width characters", "Unsichtbare Zero-Width-Zeichen"),
                description=desc,
                score=score,
                evidence=context(text, s0, rest[0][1]),
                location=Location(start=s0, end=rest[-1][1], line=line_of(text, s0),
                                  ranges=[[s, e, ""] for s, e in rest]),
                tags=["hidden"],
            ))
    if soft:
        inside = sum(1 for i in soft if 0 < i < n - 1 and text[i - 1].isalpha() and text[i + 1].isalpha())
        findings.append(Finding(
            category="unicode",
            rule="unicode.soft_hyphen",
            title=T("Soft hyphens (U+00AD)", "Weiche Trennstriche (U+00AD)"),
            description=T(f"{len(soft)} soft hyphens, {inside} of them inside words. Usually harmless (copied from a web "
                          "page), but they can evade word filters.",
                          f"{len(soft)} weiche Trennstriche, {inside} davon mitten in Wörtern. Meist harmlos "
                          "(Webseiten-Kopie), können aber Wortfilter umgehen."),
            score=12.0 if len(soft) < 20 else 18.0,
            evidence=context(text, soft[0], soft[0] + 1),
            location=Location(start=soft[0], end=soft[-1] + 1, line=line_of(text, soft[0]),
                              ranges=[[i, i + 1, ""] for i in soft]),
            tags=["hidden"],
        ))

    # --- Bidi controls ------------------------------------------------------
    bidi = [i for i, ch in enumerate(text) if ord(ch) in U.BIDI_CONTROLS]
    if bidi:
        rtl = _has_rtl(text)
        overrides = [i for i in bidi if ord(text[i]) in U.BIDI_OVERRIDES]
        isolates = [i for i in bidi if 0x2066 <= ord(text[i]) <= 0x2069]
        if overrides:
            score = 55.0
        elif isolates and not rtl:
            score = 35.0
        elif not rtl:
            score = 15.0
        else:
            score = 5.0
        if score >= 10:
            findings.append(Finding(
                category="unicode",
                rule="unicode.bidi",
                title=T("Bidi control characters (text direction manipulation)",
                        "Bidi-Steuerzeichen (Textrichtungs-Manipulation)"),
                description=T(f"{len(bidi)} text direction control characters"
                              + (f", {len(overrides)} of them overrides" if overrides else "")
                              + ". The displayed order can differ from the text that is actually read (Trojan Source).",
                              f"{len(bidi)} Steuerzeichen für die Schreibrichtung"
                              + (f", davon {len(overrides)} Overrides" if overrides else "")
                              + ". Damit kann die angezeigte Reihenfolge vom tatsächlich gelesenen Text abweichen "
                                "(Trojan-Source)."),
                score=score,
                evidence=context(text, bidi[0], bidi[0] + 1),
                location=Location(start=bidi[0], end=bidi[-1] + 1, line=line_of(text, bidi[0]),
                                  ranges=[[i, i + 1, ""] for i in bidi]),
                tags=["hidden"],
            ))

    # --- Private use area -------------------------------------------------
    pua = [i for i, ch in enumerate(text) if U.is_private_use(ord(ch))]
    if pua:
        findings.append(Finding(
            category="unicode",
            rule="unicode.private_use",
            title=T("Private use area characters", "Zeichen aus dem Private-Use-Bereich"),
            description=T(f"{len(pua)} characters without a standardized meaning – they can carry hidden data.",
                          f"{len(pua)} Zeichen ohne standardisierte Bedeutung – können versteckte Daten tragen."),
            score=15.0 if len(pua) < 50 else 20.0,
            evidence=context(text, pua[0], pua[0] + 1),
            location=Location(start=pua[0], end=pua[-1] + 1, line=line_of(text, pua[0]),
                              ranges=[[i, i + 1, ""] for i in pua]),
        ))

    findings.extend(_homoglyph_findings(text))
    findings.extend(_styled_letter_findings(text))
    findings.extend(_control_findings(text))
    findings.extend(_terminal_findings(text))
    return findings


# C0/C1 control characters except tab, line feeds, carriage return and ESC / VT / FF (handled elsewhere)
_CONTROL = re.compile("[\x00-\x08\x0e-\x1a\x1c-\x1f\x7f-\x9f]")


def _control_findings(text: str) -> list:
    findings = []
    # --- Control characters ---------------------------------------------
    ctrl = [m.start() for m in _CONTROL.finditer(text)]
    if ctrl:
        findings.append(Finding(
            category="unicode",
            rule="unicode.control",
            title=T("Non-printable control characters", "Nicht druckbare Steuerzeichen"),
            description=T(f"{len(ctrl)} control characters (C0/C1) that do not occur in normal text.",
                          f"{len(ctrl)} Steuerzeichen (C0/C1), die in normalem Text nicht vorkommen."),
            score=30.0 if len(ctrl) > 2 else 18.0,
            evidence=context(text, ctrl[0], ctrl[0] + 1),
            location=Location(start=ctrl[0], end=ctrl[-1] + 1, line=line_of(text, ctrl[0]),
                              ranges=[[i, i + 1, ""] for i in ctrl]),
        ))
    return findings


_WORD = re.compile(r"[^\W\d_]{2,}")


def _homoglyph_findings(text: str) -> list:
    latin = other = 0
    for ch in text:
        sc = U.script_of(ch)
        if sc == "LATIN":
            latin += 1
        elif sc in U.LATIN_LIKE_SCRIPTS_FOR_MIXING:
            other += 1
    if not other:
        return []
    mostly_latin = latin > 0 and other / (latin + other) < 0.15
    ranges = []
    words = []
    for m in _WORD.finditer(text):
        w = m.group()
        if len(w) < 4 or not all(("a" <= c.lower() <= "z") or ord(c) in U.CONFUSABLES for c in w):
            continue  # short tokens (units like kΩ) or real foreign words
        skeleton = "".join(U.CONFUSABLES.get(ord(c), c.lower()) for c in w)
        if not re.search(r"[aeiouy]", skeleton) or len(set(skeleton)) < 3:
            continue  # not word-like (e.g. spinner frames "ρββββββ")
        scripts = {U.script_of(c) for c in w}
        mixed = "LATIN" in scripts and scripts & set(U.LATIN_LIKE_SCRIPTS_FOR_MIXING)
        whole_fake = (mostly_latin and len(w) >= 3 and scripts and scripts <= set(U.LATIN_LIKE_SCRIPTS_FOR_MIXING))
        if not (mixed or whole_fake):
            continue
        words.append(w)
        for k, c in enumerate(w):
            if ord(c) in U.CONFUSABLES:
                rep = U.CONFUSABLES[ord(c)]
                if c.isupper():
                    rep = rep.upper()
                ranges.append([m.start() + k, m.start() + k + 1, rep])
    if not words:
        return []
    score = min(65.0, 35.0 + 5 * len(words))
    first = ranges[0][0]
    return [Finding(
        category="unicode",
        rule="unicode.homoglyph",
        title=T("Homoglyphs – look-alike letters from other scripts",
                "Homoglyphen – getarnte Buchstaben aus anderen Schriftsystemen"),
        description=T(f"{len(words)} word(s) mix Latin letters with Cyrillic/Greek look-alikes (e.g. “{words[0]}”). "
                      "This evades filters while the text looks normal to humans.",
                      f"{len(words)} Wort/Wörter mischen lateinische mit kyrillischen/griechischen Doppelgänger-Buchstaben "
                      f"(z. B. „{words[0]}“). So werden Filter umgangen, während der Text für Menschen normal aussieht."),
        score=score,
        evidence=context(text, first, first + len(words[0])),
        decoded=", ".join("".join(U.CONFUSABLES.get(ord(c), c) for c in w) for w in words[:10]),
        location=Location(start=first, end=ranges[-1][1], line=line_of(text, first), ranges=ranges),
        action="replace",
        tags=["obfuscation"],
    )]


def _is_styled(cp: int) -> bool:
    if U.emoji_letter(cp):
        return True
    ch = chr(cp)
    if 0x1D400 <= cp <= 0x1D7FF or 0xFF01 <= cp <= 0xFF5E or 0x2460 <= cp <= 0x24FF or 0x1F100 <= cp <= 0x1F1FF:
        n = unicodedata.normalize("NFKC", ch)
        return n != ch and n.isalnum()
    return False


def _styled_letter_findings(text: str) -> list:
    findings = []
    i, n = 0, len(text)
    while i < n:
        if not _is_styled(ord(text[i])):
            i += 1
            continue
        j = i
        count = 0
        ri = 0
        while j < n and (_is_styled(ord(text[j])) or (text[j] in " ‍" and j + 1 < n and _is_styled(ord(text[j + 1])))):
            if _is_styled(ord(text[j])):
                count += 1
                if 0x1F1E6 <= ord(text[j]) <= 0x1F1FF:
                    ri += 1
            j += 1
        needed = 8 if ri == count else 4
        if count >= needed:
            folded = "".join(U.fold_char(c) for c in text[i:j])
            ps, hits = payload_score(folded)
            findings.append(Finding(
                category="unicode",
                rule="unicode.styled_letters",
                title=T("Text written with emoji/special letters", "Text aus Emoji-/Sonderzeichen-Buchstaben"),
                description=T(f"{count} characters are styled letters (emoji letters, regional indicators, "
                              "mathematical or full-width characters) that AI models read as normal text.",
                              f"{count} Zeichen sind stilisierte Buchstaben (Emoji-Buchstaben, Regional-Indicator, "
                              "mathematische oder Vollbreiten-Zeichen), die KI-Modelle als normalen Text lesen.")
                + _payload_note(hits),
                score=max(20.0, min(100.0, ps + 15)) if hits else 20.0,
                evidence=visible_repr(text[i:j]),
                decoded=folded,
                location=Location(start=i, end=j, line=line_of(text, i), ranges=[[i, j, folded]]),
                action="replace",
                replacement=folded,
                default_remove=bool(hits),
                tags=["emoji", "obfuscation"],
            ))
        i = max(j, i + 1)
    return findings


_ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_LINE_BREAK = re.compile(r"[\r\n]")
_CONCEAL = re.compile(r"\x1b\[(?:[0-9;]*;)?8m(.*?)(?:\x1b\[(?:0|28)?(?:;[0-9;]*)?m|$)", re.S)


def _terminal_findings(text: str) -> list:
    findings = []
    if "\x1b" in text:
        for m in _CONCEAL.finditer(text):
            hidden = _ANSI.sub("", m.group(1))
            ps, hits = payload_score(hidden)
            findings.append(Finding(
                category="hidden",
                rule="ansi.conceal",
                title=T("Text hidden by an ANSI code (conceal)", "Per ANSI-Code verborgener Text (Conceal)"),
                description=T("The ANSI code ESC[8m makes text invisible in a terminal.",
                              "Der ANSI-Code ESC[8m macht Text im Terminal unsichtbar.") + _payload_note(hits),
                score=max(60.0, min(100.0, ps + 20)),
                evidence=visible_repr(m.group(0)),
                decoded=hidden,
                location=Location(start=m.start(), end=m.end(), line=line_of(text, m.start())),
                tags=["hidden"],
            ))
        seqs = list(_ANSI.finditer(text))
        if seqs:
            cursor = [m for m in seqs if m.group(0)[-1] in "ABCDEFGHJKSTfu" and m.group(0).startswith("\x1b[")]
            findings.append(Finding(
                category="unicode",
                rule="ansi.escape",
                title=T("ANSI escape sequences", "ANSI-Escape-Sequenzen"),
                description=T(f"{len(seqs)} terminal control sequences"
                              + (f", {len(cursor)} of them cursor/erase commands that can overwrite text in a terminal"
                                 if cursor else "") + ".",
                              f"{len(seqs)} Terminal-Steuersequenzen"
                              + (f", davon {len(cursor)} Cursor-/Löschbefehle, mit denen Text im Terminal überschrieben "
                                 "werden kann" if cursor else "") + "."),
                score=40.0 if cursor else 25.0,
                evidence=visible_repr(seqs[0].group(0)),
                location=Location(start=seqs[0].start(), end=seqs[-1].end(), line=line_of(text, seqs[0].start()),
                                  ranges=[[m.start(), m.end(), ""] for m in seqs]),
            ))
    # a lone CR with text before it (back to the previous line break) and text after it; one linear pass
    # over the line breaks (a regex like ([^\r\n]+)\r is quadratic on long lines, e.g. minified HTML)
    prev = -1
    for br in (_LINE_BREAK.finditer(text) if "\r" in text else ()):
        p, start = br.start(), prev + 1
        prev = p
        if text[p] != "\r" or p == start or p + 1 >= len(text) or text[p + 1] in "\r\n":
            continue
        hidden = text[start:p]
        ps, hits = payload_score(hidden)
        findings.append(Finding(
            category="hidden",
            rule="layout.carriage_return",
            title=T("Overwritten text (carriage return)", "Überschriebener Text (Wagenrücklauf)"),
            description=T("A lone CR (\\r) makes the following text overwrite the previous one in terminals – "
                          "the first part is invisible to humans.",
                          "Ein einzelnes CR (\\r) lässt nachfolgenden Text den vorherigen in Terminals überschreiben – "
                          "der vordere Teil ist für Menschen unsichtbar.") + _payload_note(hits),
            score=max(35.0, min(100.0, ps + 20)) if hits else 35.0,
            evidence=visible_repr(text[start:p + 1].replace("\r", "⟦CR⟧")),
            decoded=hidden,
            location=Location(start=start, end=p + 1, line=line_of(text, start)),
            tags=["hidden"],
        ))
    return findings


# ---------------------------------------------------------------------------
# Encoded payloads
# ---------------------------------------------------------------------------

_B64 = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{24,}={0,2}(?![A-Za-z0-9+/=_-])")
_HEX = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[ :]?){12,}(?![0-9A-Fa-f])")
_ESC_HEX = re.compile(r"(?:\\x[0-9A-Fa-f]{2}){8,}")
_URLENC = re.compile(r"[A-Za-z0-9+._~-]*(?:%[0-9A-Fa-f]{2}[A-Za-z0-9+._~-]*){6,}")
_ENTITIES = re.compile(r"(?:&#(?:x[0-9A-Fa-f]+|[0-9]+);\s?){6,}")
_BINARY = re.compile(r"(?<![01])(?:[01]{8}[ ]?){5,}(?![01])")
_UNI_ESC = re.compile(r"(?:\\u[0-9A-Fa-f]{4}){6,}")


def _texty(s: str) -> bool:
    return (len(s.strip()) >= 6 and U.printable_ratio(s) > 0.92 and U.letter_ratio(s) > 0.6)


def _decode_b64(tok: str) -> str:
    t = tok.replace("-", "+").replace("_", "/")
    t += "=" * (-len(t) % 4)
    try:
        raw = base64.b64decode(t, validate=True)
        return raw.decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return ""


def _encoded_finding(text, s, e, decoded, kind, label):
    ps, hits = payload_score(decoded)
    words = len(decoded.split())
    if hits:
        score = min(100.0, max(55.0, ps + 15))
        title = T(f"{label}-encoded instruction", f"{label}-kodierte Anweisung")
    elif words >= 4:
        score = 12.0
        title = T(f"{label}-encoded plain text", f"{label}-kodierter Klartext")
    else:
        return None
    return Finding(
        category="encoding",
        rule=f"encoding.{kind}",
        title=title,
        description=T(f"A {label} string contains readable text that an AI model could decode and follow.",
                      f"Eine {label}-Zeichenkette enthält lesbaren Text, den ein KI-Modell dekodieren und befolgen könnte.")
        + _payload_note(hits),
        score=score,
        evidence=visible_repr(text[s:e][:200]),
        decoded=decoded[:2000],
        location=Location(start=s, end=e, line=line_of(text, s)),
        default_remove=bool(hits),
        tags=["encoded"],
    )


def encoded_findings(text: str) -> list:
    findings = []
    for m in _B64.finditer(text):
        tok = m.group()
        pre = text[max(0, m.start() - 40):m.start()].lower()
        if "base64," in pre and "data:" in pre and "image" in pre:
            continue
        if not (re.search(r"[0-9+/=]", tok) or (re.search(r"[a-z]", tok) and re.search(r"[A-Z]", tok))):
            continue
        dec = _decode_b64(tok)
        if dec and _texty(dec):
            f = _encoded_finding(text, m.start(), m.end(), dec, "base64", "Base64")
            if f:
                findings.append(f)
    for m in _HEX.finditer(text):
        h = re.sub(r"[ :]", "", m.group())
        try:
            dec = bytes.fromhex(h[: len(h) - len(h) % 2]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if _texty(dec):
            f = _encoded_finding(text, m.start(), m.end(), dec, "hex", "Hex")
            if f:
                findings.append(f)
    for m in (_ESC_HEX.finditer(text) if "\\x" in text else ()):
        try:
            dec = bytes.fromhex(m.group().replace("\\x", "")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if _texty(dec):
            f = _encoded_finding(text, m.start(), m.end(), dec, "hex_escape", "Hex-Escape")
            if f:
                findings.append(f)
    for m in (_UNI_ESC.finditer(text) if "\\u" in text else ()):
        try:
            dec = codecs.decode(m.group(), "unicode_escape")
        except Exception:
            continue
        if _texty(dec):
            f = _encoded_finding(text, m.start(), m.end(), dec, "unicode_escape", "Unicode-Escape")
            if f:
                findings.append(f)
    for m in (_URLENC.finditer(text) if "%" in text else ()):
        dec = urllib.parse.unquote_plus(m.group())
        if dec != m.group() and _texty(dec):
            f = _encoded_finding(text, m.start(), m.end(), dec, "url", "URL")
            if f:
                findings.append(f)
    for m in (_ENTITIES.finditer(text) if "&#" in text else ()):
        dec = html.unescape(m.group())
        if _texty(dec):
            f = _encoded_finding(text, m.start(), m.end(), dec, "html_entities", "HTML-Entity")
            if f:
                findings.append(f)
    for m in _BINARY.finditer(text):
        bits = m.group().replace(" ", "")
        try:
            dec = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits) - len(bits) % 8, 8)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if _texty(dec):
            f = _encoded_finding(text, m.start(), m.end(), dec, "binary", "Binary")
            if f:
                findings.append(f)

    # ROT13 and reversed text: only strong rules count to keep false positives low.
    for label, kind, transform, mapper in (
        ("ROT13", "rot13", lambda t: codecs.encode(t, "rot13"), lambda s, e, n: (s, e)),
        (T("reversed", "rückwärts"), "reversed", lambda t: t[::-1], lambda s, e, n: (n - e, n - s)),
    ):
        strong = transformed_hits(text, transform)
        plain = {(h.rule.id, h.start, h.end) for h in find_hits(text)} if strong else set()
        for h in strong:
            s, e = mapper(h.start, h.end, len(text))
            if (h.rule.id, s, e) in plain or transform(text[s:e]) == text[s:e]:
                continue
            s, e = expand_to_sentence(text, s, e)
            seg = transform(text[s:e])
            findings.append(Finding(
                category="encoding",
                rule=f"encoding.{kind}",
                title=T("Obfuscated instruction (", "Verschleierte Anweisung (") + label + ")",
                description=T("Decoding (", "Nach Dekodierung (") + label
                + T(") reveals an injection instruction (", ") ergibt sich eine Injection-Anweisung (")
                + CATEGORY_TITLES[h.rule.category] + ").",
                score=min(100.0, h.rule.weight + 10),
                evidence=visible_repr(text[s:e]),
                decoded=seg,
                location=Location(start=s, end=e, line=line_of(text, s)),
                tags=["encoded"],
            ))
    return findings


# ---------------------------------------------------------------------------
# Layout tricks in plain text
# ---------------------------------------------------------------------------

def layout_findings(text: str) -> list:
    findings = []
    for m in re.finditer(r"[ \t]{60,}(\S[^\n]*)", text):
        hidden = m.group(1)
        line_start = text.rfind("\n", 0, m.start()) + 1
        line = text[line_start:m.end()]
        if not text[line_start:m.start()].strip() and len(m.group(0)) - len(hidden) < 120:
            continue  # deep indentation (code continuation lines) is not hiding anything
        if hidden.lstrip().startswith(("|", "+", "#", "//", "*")) or line.count("|") >= 2:
            continue  # table padding / aligned code comments
        if sum(c.isalpha() for c in hidden) < 8:
            continue
        ps, hits = payload_score(hidden)
        findings.append(Finding(
            category="hidden",
            rule="layout.far_right",
            title=T("Text pushed far to the right", "Weit nach rechts verschobener Text"),
            description=T(f"Text follows {len(m.group(0)) - len(hidden)} spaces and is not visible in many editors/views.",
                          f"Text steht hinter {len(m.group(0)) - len(hidden)} Leerzeichen und ist in vielen "
                          "Editoren/Ansichten nicht sichtbar.") + _payload_note(hits),
            score=min(100.0, ps + 25) if hits else 30.0,
            evidence=visible_repr(hidden),
            decoded=hidden,
            location=Location(start=m.start(1), end=m.end(1), line=line_of(text, m.start(1))),
            tags=["hidden"],
        ))
    for m in re.finditer(r"(?:[ \t]*\r?\n){15,}", text):
        tail_start = m.end()
        nxt = re.search(r"(?:[ \t]*\r?\n){3,}", text[tail_start:])
        tail_end = tail_start + nxt.start() if nxt else len(text)
        hidden = text[tail_start:tail_end]
        if len(hidden.strip()) < 3:
            continue
        ps, hits = payload_score(hidden)
        findings.append(Finding(
            category="hidden",
            rule="layout.blank_gap",
            title=T("Text after many blank lines", "Text nach vielen Leerzeilen"),
            description=T(f"After {m.group(0).count(chr(10))} blank lines more text follows that is easily overlooked.",
                          f"Nach {m.group(0).count(chr(10))} Leerzeilen folgt weiterer Text, der beim Lesen leicht "
                          "übersehen wird.") + _payload_note(hits),
            score=min(100.0, ps + 20) if hits else 18.0,
            evidence=visible_repr(hidden[:300]),
            location=Location(start=tail_start, end=tail_end, line=line_of(text, tail_start)),
            default_remove=bool(hits),
            tags=["hidden"],
        ))
    return findings


def analyze_text(text: str, include_layout: bool = True) -> list:
    findings = []
    findings.extend(pattern_findings(text))
    findings.extend(unicode_findings(text))
    findings.extend(encoded_findings(text))
    if include_layout:
        findings.extend(layout_findings(text))
    return findings
