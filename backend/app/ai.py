from __future__ import annotations

import html
import json
import os
import re
import time
from difflib import SequenceMatcher
from typing import Any

import httpx
from dotenv import load_dotenv

from app.prompts import build_judge_prompt, build_svg_prompt
from app.svg_sanitizer import sanitize_svg


load_dotenv()

ARTIST_MODELS = [
    {
        "tier": "low",
        "model": os.getenv("ARTIST_MODEL_LOW", "openai/gpt-5-nano"),
        "reasoning_effort": os.getenv("ARTIST_MODEL_LOW_EFFORT", "low"),
    },
    {
        "tier": "mid",
        "model": os.getenv("ARTIST_MODEL_MID", "deepseek/deepseek-v3.2"),
        "reasoning_effort": os.getenv("ARTIST_MODEL_MID_EFFORT") or None,
    },
    {
        "tier": "high",
        "model": os.getenv("ARTIST_MODEL_HIGH", "openai/gpt-5.2"),
        "reasoning_effort": os.getenv("ARTIST_MODEL_HIGH_EFFORT", "high"),
    },
]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "how",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def get_ai_status() -> dict[str, Any]:
    return {
        "runtime_provider": "openrouter" if os.getenv("OPENROUTER_API_KEY") else "local_mock",
        "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
        "artist_models": [
            {
                "tier": model["tier"],
                "model": model["model"],
                "reasoning_effort": model["reasoning_effort"],
            }
            for model in ARTIST_MODELS
        ],
        "judge_model": os.getenv("OPENROUTER_JUDGE_MODEL") or "local_similarity",
    }


async def generate_artist_svg(challenge: str, model_config: dict[str, str | None]) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return sanitize_svg(_mock_svg(challenge, model_config["tier"]))

    raw_svg = await _call_openrouter_svg(api_key, challenge, model_config)
    return sanitize_svg(raw_svg)


async def score_guess(original: str, guess: str) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    judge_model = os.getenv("OPENROUTER_JUDGE_MODEL")
    if api_key and judge_model:
        try:
            return await _call_openrouter_judge(api_key, judge_model, original, guess)
        except Exception:
            pass
    return _local_score(original, guess)


async def _call_openrouter_svg(api_key: str, challenge: str, model_config: dict[str, str | None]) -> str:
    payload = {
        "model": model_config["model"],
        "messages": [{"role": "user", "content": build_svg_prompt(challenge)}],
        "temperature": 0.7,
        "max_tokens": 5000,
    }
    if model_config.get("reasoning_effort"):
        payload["reasoning_effort"] = model_config["reasoning_effort"]

    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("APP_PUBLIC_URL", "http://localhost:8081"),
                "X-Title": "AI Pictionary MVP",
            },
            json=payload,
        )
        response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def _call_openrouter_judge(api_key: str, model: str, original: str, guess: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_judge_prompt(original, guess)}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("APP_PUBLIC_URL", "http://localhost:8081"),
                "X-Title": "AI Pictionary MVP",
            },
            json=payload,
        )
        response.raise_for_status()
    result = json.loads(response.json()["choices"][0]["message"]["content"])
    return {
        "score": int(result.get("score", 0)),
        "matched_parts": list(result.get("matched_parts", [])),
        "missed_parts": list(result.get("missed_parts", [])),
        "short_feedback": str(result.get("short_feedback", "Scored by semantic judge.")),
    }


def _local_score(original: str, guess: str) -> dict[str, Any]:
    original_words = _keywords(original)
    guess_words = _keywords(guess)
    overlap = sorted(original_words & guess_words)
    missed = sorted(original_words - guess_words)
    word_score = len(overlap) / max(len(original_words), 1)
    phrase_score = SequenceMatcher(None, original.lower(), guess.lower()).ratio()
    score = round((word_score * 0.72 + phrase_score * 0.28) * 100)

    if score >= 82:
        feedback = "Strong guess. The important parts are mostly there."
    elif score >= 55:
        feedback = "Close enough to feel warm, but a few key clues are missing."
    else:
        feedback = "Different idea. Try naming the main objects and the action."

    return {
        "score": max(0, min(100, score)),
        "matched_parts": overlap[:8],
        "missed_parts": missed[:8],
        "short_feedback": feedback,
    }


def _keywords(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-zA-Z0-9']+", text.lower())
        if len(word) > 2 and word not in STOPWORDS
    }


def _ordered_keywords(text: str) -> list[str]:
    seen = set()
    ordered = []
    for word in re.findall(r"[a-zA-Z0-9']+", text.lower()):
        if len(word) <= 2 or word in STOPWORDS or word in seen:
            continue
        seen.add(word)
        ordered.append(word)
    return ordered


def _mock_svg(challenge: str, tier: str) -> str:
    words = [html.escape(word.title()) for word in _ordered_keywords(challenge)[:5]]
    label_one = words[0] if words else "Idea"
    label_two = words[1] if len(words) > 1 else "Clue"
    label_three = words[2] if len(words) > 2 else "Action"
    seed = sum(ord(char) for char in challenge + tier)
    x_offset = seed % 120
    wobble = 18 if tier == "low" else 8 if tier == "mid" else 0
    palette = {
        "low": ("#FFE066", "#FF6B5F", "#1F2937"),
        "mid": ("#70D6C9", "#4E79FF", "#172554"),
        "high": ("#F8FAFC", "#53C2A8", "#111827"),
    }[tier]

    return f"""
<svg viewBox="0 0 1024 1024" width="1024" height="1024" role="img" aria-label="AI drawing clue">
  <rect x="0" y="0" width="1024" height="1024" fill="{palette[0]}"/>
  <circle cx="{250 + x_offset}" cy="{270 + wobble}" r="96" fill="#FFFFFF" opacity="0.92"/>
  <rect x="{520 - x_offset // 3}" y="{210 + wobble}" width="210" height="150" rx="32" fill="#FFFFFF" opacity="0.92"/>
  <path d="M210 650 C320 500, 450 790, 575 620 S795 585, 840 725" fill="none" stroke="{palette[2]}" stroke-width="30" stroke-linecap="round"/>
  <polygon points="488,486 606,420 725,486 725,650 488,650" fill="{palette[1]}" opacity="0.88"/>
  <rect x="530" y="542" width="154" height="108" rx="12" fill="#FFFFFF"/>
  <line x1="552" y1="568" x2="552" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <line x1="590" y1="568" x2="590" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <line x1="628" y1="568" x2="628" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <line x1="666" y1="568" x2="666" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <text x="512" y="122" font-size="56" font-family="Arial" font-weight="700" text-anchor="middle" fill="{palette[2]}">{label_one}</text>
  <text x="268" y="292" font-size="38" font-family="Arial" font-weight="700" text-anchor="middle" fill="{palette[2]}">{label_two}</text>
  <text x="625" y="300" font-size="36" font-family="Arial" font-weight="700" text-anchor="middle" fill="{palette[2]}">{label_three}</text>
  <text x="512" y="888" font-size="32" font-family="Arial" text-anchor="middle" fill="{palette[2]}">{tier} sketch</text>
</svg>
"""
