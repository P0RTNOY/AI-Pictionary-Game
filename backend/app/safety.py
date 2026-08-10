from __future__ import annotations

import re

from fastapi import HTTPException


BLOCKED_PROMPT_PATTERNS = [
    re.compile(r"<\s*script", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"data\s*:", re.I),
]


def validate_challenge_prompt(prompt: str) -> str:
    normalized = " ".join(prompt.strip().split())
    if len(normalized) < 6:
        raise HTTPException(status_code=422, detail="Prompt is too short")
    if len(normalized) > 240:
        raise HTTPException(status_code=422, detail="Prompt is too long")
    if any(pattern.search(normalized) for pattern in BLOCKED_PROMPT_PATTERNS):
        raise HTTPException(status_code=422, detail="Prompt contains unsupported markup or URL content")
    return normalized
