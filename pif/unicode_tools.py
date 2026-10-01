"""Unicode knowledge: invisible characters, smuggling decoders, confusables.

Everything in here is table driven and deterministic.
"""
from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Character classes
# ---------------------------------------------------------------------------

ZERO_WIDTH = {
    0x200B: "ZERO WIDTH SPACE",
    0x200C: "ZERO WIDTH NON-JOINER",
    0x200D: "ZERO WIDTH JOINER",
    0x2060: "WORD JOINER",
    0x2061: "FUNCTION APPLICATION",
    0x2062: "INVISIBLE TIMES",
    0x2063: "INVISIBLE SEPARATOR",
    0x2064: "INVISIBLE PLUS",
    0xFEFF: "ZERO WIDTH NO-BREAK SPACE / BOM",
    0x180E: "MONGOLIAN VOWEL SEPARATOR",
    0x034F: "COMBINING GRAPHEME JOINER",
    0x00AD: "SOFT HYPHEN",
    0x115F: "HANGUL CHOSEONG FILLER",
    0x1160: "HANGUL JUNGSEONG FILLER",
    0x3164: "HANGUL FILLER",
    0xFFA0: "HALFWIDTH HANGUL FILLER",
    0x2800: "BRAILLE PATTERN BLANK",
    0x17B4: "KHMER VOWEL INHERENT AQ",
    0x17B5: "KHMER VOWEL INHERENT AA",
    0x206A: "INHIBIT SYMMETRIC SWAPPING",
    0x206B: "ACTIVATE SYMMETRIC SWAPPING",
    0x206C: "INHIBIT ARABIC FORM SHAPING",
    0x206D: "ACTIVATE ARABIC FORM SHAPING",
    0x206E: "NATIONAL DIGIT SHAPES",
    0x206F: "NOMINAL DIGIT SHAPES",
    0xFFF9: "INTERLINEAR ANNOTATION ANCHOR",
    0xFFFA: "INTERLINEAR ANNOTATION SEPARATOR",
    0xFFFB: "INTERLINEAR ANNOTATION TERMINATOR",
    0x1D159: "MUSICAL SYMBOL NULL NOTEHEAD",
    0x1D173: "MUSICAL SYMBOL BEGIN BEAM",
    0x1D174: "MUSICAL SYMBOL END BEAM",
    0x1D175: "MUSICAL SYMBOL BEGIN TIE",
    0x1D176: "MUSICAL SYMBOL END TIE",
    0x1D177: "MUSICAL SYMBOL BEGIN SLUR",
    0x1D178: "MUSICAL SYMBOL END SLUR",
    0x1D179: "MUSICAL SYMBOL BEGIN PHRASE",
    0x1D17A: "MUSICAL SYMBOL END PHRASE",
}

BIDI_CONTROLS = {
    0x061C: "ARABIC LETTER MARK",
    0x200E: "LEFT-TO-RIGHT MARK",
    0x200F: "RIGHT-TO-LEFT MARK",
    0x202A: "LEFT-TO-RIGHT EMBEDDING",
    0x202B: "RIGHT-TO-LEFT EMBEDDING",
    0x202C: "POP DIRECTIONAL FORMATTING",
    0x202D: "LEFT-TO-RIGHT OVERRIDE",
    0x202E: "RIGHT-TO-LEFT OVERRIDE",
    0x2066: "LEFT-TO-RIGHT ISOLATE",
    0x2067: "RIGHT-TO-LEFT ISOLATE",
    0x2068: "FIRST STRONG ISOLATE",
    0x2069: "POP DIRECTIONAL ISOLATE",
}
BIDI_OVERRIDES = {0x202A, 0x202B, 0x202D, 0x202E}

ODD_SPACES = {
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008,
    0x2009, 0x200A, 0x202F, 0x205F, 0x3000, 0x1680,
}


def is_tag(cp: int) -> bool:
    return 0xE0000 <= cp <= 0xE007F


def is_variation_selector(cp: int) -> bool:
    return 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF


def is_private_use(cp: int) -> bool:
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def is_control(cp: int) -> bool:
    if cp in (0x09, 0x0A, 0x0D):
        return False
    return cp < 0x20 or 0x7F <= cp <= 0x9F


def is_invisible(cp: int) -> bool:
    """Characters that render as nothing (or are not meant to be seen)."""
    return (
        cp in ZERO_WIDTH
        or cp in BIDI_CONTROLS
        or is_tag(cp)
        or is_variation_selector(cp)
        or (is_control(cp) and cp != 0x1B)
        or unicodedata.category(chr(cp)) == "Cf"
    )


def is_emoji_like(cp: int) -> bool:
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2300 <= cp <= 0x23FF
        or 0x2B00 <= cp <= 0x2BFF
        or 0x2190 <= cp <= 0x21FF
        or 0x25A0 <= cp <= 0x25FF
        or 0x2934 <= cp <= 0x2935
        or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299, 0x20E3)
    )


def is_cjk(cp: int) -> bool:
    return (
        0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x3134F
    )


def char_name(cp: int) -> str:
    if cp in ZERO_WIDTH:
        return ZERO_WIDTH[cp]
    if cp in BIDI_CONTROLS:
        return BIDI_CONTROLS[cp]
    if is_tag(cp):
        return "TAG CHARACTER"
    if is_variation_selector(cp):
        return "VARIATION SELECTOR"
    try:
        return unicodedata.name(chr(cp))
    except ValueError:
        return f"U+{cp:04X}"


# ---------------------------------------------------------------------------
# Smuggling decoders
# ---------------------------------------------------------------------------

def decode_tags(s: str) -> str:
    """Unicode tag block (U+E0000..E007F) mirrors ASCII -> "ASCII smuggling"."""
    out = []
    for ch in s:
        cp = ord(ch)
        if 0xE0020 <= cp <= 0xE007E:
            out.append(chr(cp - 0xE0000))
        elif cp == 0xE007F:
            out.append("")  # CANCEL TAG
    return "".join(out)


def vs_to_byte(cp: int):
    if 0xFE00 <= cp <= 0xFE0F:
        return cp - 0xFE00
    if 0xE0100 <= cp <= 0xE01EF:
        return cp - 0xE0100 + 16
    return None


def decode_variation_selectors(s: str) -> str:
    """Decode bytes hidden in runs of variation selectors (emoji smuggling).

    Each selector VS1..VS256 carries one byte (0..255)."""
    data = bytearray()
    for ch in s:
        b = vs_to_byte(ord(ch))
        if b is not None:
            data.append(b)
    return data.decode("utf-8", errors="replace")


def printable_ratio(s: str) -> float:
    if not s:
        return 0.0
    good = sum(1 for c in s if c.isprintable() or c in "\n\r\t")
    return good / len(s)


def letter_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(1 for c in s if c.isalpha() or c == " ") / len(s)


def decode_zero_width_binary(s: str) -> str:
    """Try to decode zero-width steganography (bits encoded as invisible chars).

    Supports the common schemes: two symbols as 0/1 in 8-bit groups, and three
    symbols where one acts as a separator between variable-length binary words.
    Returns the best decoding or "" if nothing plausible is found."""
    chars = [c for c in s if ord(c) in ZERO_WIDTH or ord(c) in BIDI_CONTROLS]
    distinct = sorted(set(chars))
    candidates = []
    if len(distinct) == 2 and len(chars) >= 8:
        for zero, one in ((distinct[0], distinct[1]), (distinct[1], distinct[0])):
            bits = "".join("0" if c == zero else "1" for c in chars)
            for width in (8, 7):
                usable = len(bits) - len(bits) % width
                if usable < width:
                    continue
                raw = bytes(int(bits[i:i + width], 2) for i in range(0, usable, width))
                candidates.append(raw.decode("utf-8", errors="replace"))
    if len(distinct) == 3 and len(chars) >= 8:
        for sep in distinct:
            others = [c for c in distinct if c != sep]
            for zero, one in ((others[0], others[1]), (others[1], others[0])):
                words = "".join(chars).split(sep)
                out = []
                for w in words:
                    if not w:
                        continue
                    try:
                        v = int("".join("0" if c == zero else "1" for c in w), 2)
                        out.append(chr(v) if v < 0x110000 else "?")
                    except ValueError:
                        out.append("?")
                candidates.append("".join(out))
    best = ""
    best_q = 0.0
    for c in candidates:
        q = printable_ratio(c) * 0.5 + letter_ratio(c) * 0.5
        if q > best_q:
            best, best_q = c, q
    if best_q >= 0.8 and len(best.strip()) >= 2:
        return best
    return ""


# ---------------------------------------------------------------------------
# Confusables / letter-like symbols -> Latin skeleton
# ---------------------------------------------------------------------------

_CONFUSABLE_PAIRS = {
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
    "с": "c", "т": "t", "у": "y", "х": "x", "ѕ": "s", "і": "i", "ї": "i", "ј": "j", "һ": "h",
    "ԁ": "d", "ԛ": "q", "ԝ": "w", "ɡ": "g", "ӏ": "l", "ь": "b", "п": "n", "г": "r", "ո": "n",
    "А": "a", "В": "b", "Е": "e", "К": "k", "М": "m", "Н": "h", "О": "o", "Р": "p", "С": "c",
    "Т": "t", "У": "y", "Х": "x", "Ѕ": "s", "І": "i", "Ј": "j", "Ԁ": "d", "Ԛ": "q", "Ԝ": "w",
    # Greek
    "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
    "υ": "u", "χ": "x", "γ": "y", "ω": "w", "Α": "a", "Β": "b", "Ε": "e", "Ζ": "z", "Η": "h",
    "Ι": "i", "Κ": "k", "Μ": "m", "Ν": "n", "Ο": "o", "Ρ": "p", "Τ": "t", "Υ": "y", "Χ": "x",
    # Armenian / Cherokee / misc lookalikes
    "օ": "o", "ս": "u", "ց": "g", "հ": "h", "Ꭺ": "a", "Ꭼ": "e", "Ꮃ": "w", "Ꮪ": "s", "Ꭲ": "t",
    "ı": "i", "ȷ": "j", "ℓ": "l", "ℯ": "e", "℮": "e",
    # Small capitals and IPA
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ɢ": "g", "ʜ": "h", "ɪ": "i",
    "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ǫ": "q", "ʀ": "r",
    "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ʏ": "y", "ᴢ": "z",
}
CONFUSABLES = {ord(k): v for k, v in _CONFUSABLE_PAIRS.items()}

LATIN_LIKE_SCRIPTS_FOR_MIXING = ("CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE")


def emoji_letter(cp: int):
    """Letters written with emoji/enclosed symbols that NFKC does not fold."""
    if 0x1F1E6 <= cp <= 0x1F1FF:  # regional indicator symbols
        return chr(ord("a") + cp - 0x1F1E6)
    if 0x1F150 <= cp <= 0x1F169:  # negative circled latin capital letters
        return chr(ord("a") + cp - 0x1F150)
    if 0x1F170 <= cp <= 0x1F189:  # negative squared latin capital letters
        return chr(ord("a") + cp - 0x1F170)
    if 0x1F130 <= cp <= 0x1F149:  # squared latin capital letters
        return chr(ord("a") + cp - 0x1F130)
    return None


def fold_char(ch: str) -> str:
    """Map a single character to its lowercase Latin skeleton (may be '' or >1 chars)."""
    cp = ord(ch)
    if cp in CONFUSABLES:
        return CONFUSABLES[cp]
    el = emoji_letter(cp)
    if el:
        return el
    n = unicodedata.normalize("NFKC", ch)
    if n != ch:
        out = []
        for c in n:
            c2 = CONFUSABLES.get(ord(c))
            out.append(c2 if c2 else c)
        return "".join(out).casefold()
    return ch.casefold()


def script_of(ch: str) -> str:
    if not ch.isalpha():
        return ""
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return ""
    return name.split(" ")[0]


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
