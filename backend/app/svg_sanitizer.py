from __future__ import annotations

import re
from io import StringIO
from xml.etree.ElementTree import Element, ParseError, tostring

from defusedxml import ElementTree as DefusedElementTree


class SvgSanitizationError(ValueError):
    pass


ALLOWED_TAGS = {
    "svg",
    "g",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
    "title",
    "desc",
    "path",
    "circle",
    "rect",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
}

ALLOWED_ATTRS = {
    "svg": {"viewBox", "width", "height", "role", "aria-label", "xmlns"},
    "*": {
        "id",
        "class",
        "d",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "width",
        "height",
        "points",
        "fill",
        "fill-opacity",
        "stroke",
        "stroke-opacity",
        "stroke-width",
        "stroke-dasharray",
        "stroke-linecap",
        "stroke-linejoin",
        "opacity",
        "offset",
        "stop-color",
        "stop-opacity",
        "clip-path",
        "mask",
        "font-size",
        "font-family",
        "font-weight",
        "font-style",
        "text-anchor",
        "dominant-baseline",
        "transform",
        "style",
    },
}

UNSAFE_VALUE = re.compile(r"(javascript:|data:|https?://|//|url\s*\(\s*['\"]?(?:https?|data|javascript):)", re.I)
MARKDOWN_FENCE = re.compile(r"```(?:svg)?|```", re.I)
MAX_SVG_BYTES = 120_000


def sanitize_svg(raw_svg: str) -> str:
    candidate = _extract_svg(raw_svg)
    if len(candidate.encode("utf-8")) > MAX_SVG_BYTES:
        raise SvgSanitizationError("SVG is larger than the 120KB limit.")

    try:
        root = DefusedElementTree.parse(StringIO(candidate)).getroot()
    except (ParseError, DefusedElementTree.ParseError) as exc:
        raise SvgSanitizationError("Model returned invalid SVG.") from exc

    cleaned = _clean_node(root)
    if cleaned is None or _local_name(cleaned.tag) != "svg":
        raise SvgSanitizationError("SVG root element is required.")

    cleaned.set("viewBox", cleaned.get("viewBox", "0 0 1024 1024"))
    cleaned.set("width", "1024")
    cleaned.set("height", "1024")
    return tostring(cleaned, encoding="unicode", short_empty_elements=True)


def _extract_svg(raw_svg: str) -> str:
    stripped = MARKDOWN_FENCE.sub("", raw_svg).strip()
    start = stripped.lower().find("<svg")
    end = stripped.lower().rfind("</svg>")
    if start < 0 or end < 0:
        raise SvgSanitizationError("No SVG element found.")
    return stripped[start : end + len("</svg>")]


def _clean_node(node: Element) -> Element | None:
    tag = _local_name(node.tag)
    if tag not in ALLOWED_TAGS:
        return None

    cleaned = Element(tag)
    allowed = ALLOWED_ATTRS.get(tag, set()) | ALLOWED_ATTRS["*"]
    for attr, value in node.attrib.items():
        attr_name = _local_name(attr)
        if attr_name.lower().startswith("on") or attr_name not in allowed:
            continue
        if UNSAFE_VALUE.search(value):
            continue
        cleaned.set(attr_name, value)

    if node.text and tag in {"text", "tspan", "title", "desc"}:
        cleaned.text = node.text[:80]

    for child in list(node):
        child_cleaned = _clean_node(child)
        if child_cleaned is not None:
            cleaned.append(child_cleaned)

    return cleaned


def _local_name(name: str) -> str:
    if "}" in name:
        return name.rsplit("}", 1)[1]
    return name
