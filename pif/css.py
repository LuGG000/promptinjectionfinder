"""Tiny deterministic CSS helpers: color parsing, contrast, hiding rules."""
from __future__ import annotations

import colorsys
import re

from .i18n import T

NAMED_COLORS = {
    "white": (255, 255, 255), "snow": (255, 250, 250), "ivory": (255, 255, 240), "ghostwhite": (248, 248, 255),
    "whitesmoke": (245, 245, 245), "seashell": (255, 245, 238), "floralwhite": (255, 250, 240),
    "mintcream": (245, 255, 250), "azure": (240, 255, 255), "aliceblue": (240, 248, 255), "honeydew": (240, 255, 240),
    "linen": (250, 240, 230), "oldlace": (253, 245, 230), "lavenderblush": (255, 240, 245), "beige": (245, 245, 220),
    "lightyellow": (255, 255, 224), "cornsilk": (255, 248, 220), "gainsboro": (220, 220, 220),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211), "silver": (192, 192, 192),
    "darkgray": (169, 169, 169), "darkgrey": (169, 169, 169), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "dimgray": (105, 105, 105), "black": (0, 0, 0), "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "orange": (255, 165, 0), "purple": (128, 0, 128), "navy": (0, 0, 128),
    "lightblue": (173, 216, 230), "lightcyan": (224, 255, 255), "lavender": (230, 230, 250),
}


def parse_color(value: str):
    """Return (r, g, b, alpha) or None."""
    if not value:
        return None
    v = value.strip().lower().replace("!important", "").strip()
    if v in ("transparent",):
        return (0, 0, 0, 0.0)
    if v in NAMED_COLORS:
        return (*NAMED_COLORS[v], 1.0)
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            r, g, b = (int(c * 2, 16) for c in h[:3])
            a = int(h[3] * 2, 16) / 255 if len(h) == 4 else 1.0
            return (r, g, b, a)
        if len(h) in (6, 8):
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
            return (r, g, b, a)
        return None
    m = re.fullmatch(r"rgba?\(\s*([\d.]+%?)[\s,]+([\d.]+%?)[\s,]+([\d.]+%?)(?:[\s,/]+([\d.]+%?))?\s*\)", v)
    if m:
        def ch(x):
            return float(x[:-1]) * 2.55 if x.endswith("%") else float(x)

        def al(x):
            if x is None:
                return 1.0
            return float(x[:-1]) / 100 if x.endswith("%") else float(x)
        return (ch(m.group(1)), ch(m.group(2)), ch(m.group(3)), al(m.group(4)))
    m = re.fullmatch(r"hsla?\(\s*([\d.]+)(?:deg)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%(?:[\s,/]+([\d.]+%?))?\s*\)", v)
    if m:
        h, s, l = float(m.group(1)) / 360, float(m.group(2)) / 100, float(m.group(3)) / 100
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        a = m.group(4)
        alpha = 1.0 if a is None else (float(a[:-1]) / 100 if a.endswith("%") else float(a))
        return (r * 255, g * 255, b * 255, alpha)
    return None


def _lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = rgb[:3]
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse_style(style: str) -> dict:
    out = {}
    for decl in style.split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            out[k.strip().lower()] = v.strip().lower().replace("!important", "").strip()
    return out


def _px(value: str):
    m = re.match(r"(-?[\d.]+)\s*(px|pt|em|rem|%|vw|vh)?", value or "")
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2) or "px"
    if unit == "pt":
        return n * 1.333
    if unit in ("em", "rem"):
        return n * 16
    if unit == "%":
        return n * 0.16
    return n


def hiding_reasons(props: dict, bg=None) -> tuple:
    """Return (reasons, low_visibility_reasons) for a set of CSS declarations.

    ``bg`` is the effective background colour (r, g, b) of the element."""
    hard, soft = [], []
    disp = props.get("display", "")
    if disp == "none":
        hard.append("display:none")
    if props.get("visibility") in ("hidden", "collapse"):
        hard.append("visibility:hidden")
    if "opacity" in props:
        try:
            o = float(props["opacity"].rstrip("%")) / (100 if props["opacity"].endswith("%") else 1)
            if o <= 0.1:
                hard.append(f"opacity:{props['opacity']}")
            elif o <= 0.3:
                soft.append(f"opacity:{props['opacity']}")
        except ValueError:
            pass
    fs = props.get("font-size")
    if fs:
        px = _px(fs)
        if px is not None:
            if px <= 2:
                hard.append(f"font-size:{fs}")
            elif px <= 6:
                soft.append(f"font-size:{fs}")
    for dim in ("height", "max-height", "width", "max-width"):
        if dim in props:
            px = _px(props[dim])
            if px is not None and px <= 1 and (props.get("overflow") in ("hidden", "clip") or dim.startswith("max") or px <= 0):
                hard.append(f"{dim}:{props[dim]}")
    if props.get("position") in ("absolute", "fixed"):
        for side in ("left", "top", "right", "bottom"):
            px = _px(props.get(side, ""))
            if px is not None and px <= -500:
                hard.append(T(f"{side}:{props[side]} (off-screen)", f"{side}:{props[side]} (außerhalb des Sichtbereichs)"))
    ti = _px(props.get("text-indent", ""))
    if ti is not None and ti <= -500:
        hard.append(f"text-indent:{props['text-indent']}")
    clip = props.get("clip", "") + props.get("clip-path", "")
    if re.search(r"rect\(\s*0[a-z]*[\s,]+0[a-z]*[\s,]+0[a-z]*[\s,]+0", clip) or re.search(r"inset\(\s*50%|circle\(\s*0", clip):
        hard.append(T("clip (fully clipped)", "clip (vollständig abgeschnitten)"))
    if re.search(r"scale\(\s*0(\.0+)?\s*[,)]", props.get("transform", "")):
        hard.append("transform:scale(0)")
    if props.get("color") and bg != UNKNOWN_BG:
        c = parse_color(props["color"])
        if c is not None:
            if c[3] <= 0.1:
                hard.append(f"color:{props['color']} (transparent)")
            else:
                ratio = contrast_ratio(c, bg or (255, 255, 255))
                if ratio < 1.35:
                    hard.append(T(f"color:{props['color']} on its background (contrast {ratio:.2f}:1)",
                                  f"color:{props['color']} auf Hintergrund (Kontrast {ratio:.2f}:1)"))
                elif ratio < 2.0:
                    soft.append(T(f"color:{props['color']} – very low contrast ({ratio:.2f}:1)",
                                  f"color:{props['color']} – sehr schwacher Kontrast ({ratio:.2f}:1)"))
    if props.get("-webkit-text-fill-color") and bg != UNKNOWN_BG:
        c = parse_color(props["-webkit-text-fill-color"])
        if c is not None and (c[3] <= 0.1 or contrast_ratio(c, bg or (255, 255, 255)) < 1.35):
            hard.append(T("text-fill-color invisible", "text-fill-color unsichtbar"))
    return hard, soft


UNKNOWN_BG = "unknown"  # background image: the real contrast cannot be judged


_COLOR_TOKEN = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b[a-z]+\b")


def background_of(props: dict):
    """Effective background colour (r, g, b), UNKNOWN_BG for images, or None if not set."""
    for key in ("background-color", "background", "background-image"):
        val = props.get(key)
        if not val:
            continue
        if "url(" in val:
            return UNKNOWN_BG
        if "gradient(" in val:
            cols = [c for c in (parse_color(t) for t in _COLOR_TOKEN.findall(val)) if c is not None and c[3] > 0.3]
            if cols:  # average of the gradient stops
                return tuple(sum(c[i] for c in cols) / len(cols) for i in range(3))
            return UNKNOWN_BG
        for token in re.split(r"\s+(?![^(]*\))", val):
            c = parse_color(token)
            if c is not None and c[3] > 0.5:
                return c[:3]
    return None


def resolve_vars(props: dict, variables: dict) -> dict:
    """Substitute var(--name, fallback) with the collected custom properties."""
    out = {}
    for k, v in props.items():
        for _ in range(5):
            if "var(" not in v:
                break
            v = re.sub(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)",
                       lambda m: variables.get(m.group(1), m.group(2) or ""), v)
        out[k] = v.strip()
    return out
