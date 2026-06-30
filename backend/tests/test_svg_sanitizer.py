import pytest

from app.svg_sanitizer import SvgSanitizationError, sanitize_svg


def test_sanitizer_removes_scripts_and_event_handlers():
    svg = """
    <svg viewBox="0 0 10 10" onclick="alert(1)">
      <script>alert(1)</script>
      <foreignObject><div>bad</div></foreignObject>
      <circle cx="5" cy="5" r="3" fill="red" onload="alert(2)" />
    </svg>
    """

    cleaned = sanitize_svg(svg)

    assert "<script" not in cleaned
    assert "foreignObject" not in cleaned
    assert "onclick" not in cleaned
    assert "onload" not in cleaned
    assert "<circle" in cleaned


def test_sanitizer_blocks_external_references():
    svg = '<svg><rect width="10" height="10" fill="url(https://bad.example/a)" /></svg>'

    cleaned = sanitize_svg(svg)

    assert "https://bad.example" not in cleaned
    assert "<rect" in cleaned


def test_sanitizer_preserves_safe_gradients_and_clip_paths():
    svg = """
    <svg viewBox="0 0 100 100">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#8ec5ff" />
          <stop offset="100%" stop-color="#ffe066" />
        </linearGradient>
        <clipPath id="round"><circle cx="50" cy="50" r="40" /></clipPath>
      </defs>
      <rect width="100" height="100" fill="url(#sky)" clip-path="url(#round)" />
    </svg>
    """

    cleaned = sanitize_svg(svg)

    assert "linearGradient" in cleaned
    assert "stop-color" in cleaned
    assert "clip-path" in cleaned
    assert "url(#sky)" in cleaned


def test_sanitizer_rejects_non_svg():
    with pytest.raises(SvgSanitizationError):
        sanitize_svg("<html></html>")
