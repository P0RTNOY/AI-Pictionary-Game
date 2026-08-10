from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from app.prompts import build_judge_prompt, build_svg_prompt
from app.svg_sanitizer import sanitize_svg


load_dotenv()
logger = logging.getLogger("ai_pictionary.ai")

ARTIST_MODELS = [
    {
        "tier": "confusing",
        "model": os.getenv("OPENROUTER_MODEL_CONFUSING", os.getenv("ARTIST_MODEL_LOW", "openai/gpt-5-nano")),
        "reasoning_effort": os.getenv("OPENROUTER_MODEL_CONFUSING_EFFORT", os.getenv("ARTIST_MODEL_LOW_EFFORT", "low")),
    },
    {
        "tier": "balanced",
        "model": os.getenv("OPENROUTER_MODEL_BALANCED", os.getenv("ARTIST_MODEL_MID", "deepseek/deepseek-v3.2")),
        "reasoning_effort": os.getenv("OPENROUTER_MODEL_BALANCED_EFFORT", os.getenv("ARTIST_MODEL_MID_EFFORT") or "") or None,
    },
    {
        "tier": "literal",
        "model": os.getenv("OPENROUTER_MODEL_LITERAL", os.getenv("ARTIST_MODEL_HIGH", "openai/gpt-5.2")),
        "reasoning_effort": os.getenv("OPENROUTER_MODEL_LITERAL_EFFORT", os.getenv("ARTIST_MODEL_HIGH_EFFORT", "high")),
    },
]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SUPPORTED_AI_PROVIDERS = {"mock", "openrouter", "local"}
DEFAULT_PROVIDER_RESPONSE_MAX_BYTES = 1_000_000
PROVIDER_RESPONSE_LIMIT_ENV = "AI_PROVIDER_RESPONSE_MAX_BYTES"
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

ACTION_WORDS = {
    "arguing",
    "babysitting",
    "baking",
    "building",
    "cooking",
    "dancing",
    "drawing",
    "eating",
    "fighting",
    "flying",
    "giving",
    "helping",
    "juggling",
    "making",
    "playing",
    "riding",
    "singing",
    "sleeping",
    "teaching",
    "wearing",
}

SETTING_WORDS = {"beach", "castle", "city", "court", "courtroom", "forest", "kitchen", "moon", "ocean", "school", "space"}
MOOD_WORDS = {"angry", "confused", "cursed", "funny", "jealous", "sad", "scared", "sleepy", "weird"}


class AIConfigurationError(RuntimeError):
    """Raised when AI provider configuration is invalid."""


class ProviderResponseError(RuntimeError):
    """Raised when an upstream provider response cannot be safely consumed."""


def provider_response_max_bytes() -> int:
    raw_value = os.getenv(PROVIDER_RESPONSE_LIMIT_ENV)
    if raw_value is None:
        return DEFAULT_PROVIDER_RESPONSE_MAX_BYTES
    try:
        configured = int(raw_value)
    except ValueError as exc:
        raise AIConfigurationError("Invalid AI provider response limit configuration") from exc
    if configured <= 0:
        raise AIConfigurationError("Invalid AI provider response limit configuration")
    return configured


def _declared_response_is_oversized(response: httpx.Response, max_bytes: int) -> bool:
    content_length = response.headers.get("Content-Length")
    if content_length is None:
        return False
    try:
        return int(content_length) > max_bytes
    except ValueError:
        return False


def _parse_provider_json(body: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderResponseError("Provider response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderResponseError("Provider response had an invalid shape")
    return parsed


async def request_json_bounded(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_bytes: Optional[int] = None,
    **request_kwargs: Any,
) -> dict[str, Any]:
    byte_limit = max_bytes if max_bytes is not None else provider_response_max_bytes()
    async with client.stream(method, url, **request_kwargs) as response:
        response.raise_for_status()
        if _declared_response_is_oversized(response, byte_limit):
            raise ProviderResponseError("Provider response exceeded the configured size limit")
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > byte_limit:
                raise ProviderResponseError("Provider response exceeded the configured size limit")
            body.extend(chunk)
    return _parse_provider_json(bytes(body))


def request_json_bounded_sync(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_bytes: Optional[int] = None,
    **request_kwargs: Any,
) -> dict[str, Any]:
    byte_limit = max_bytes if max_bytes is not None else provider_response_max_bytes()
    with client.stream(method, url, **request_kwargs) as response:
        response.raise_for_status()
        if _declared_response_is_oversized(response, byte_limit):
            raise ProviderResponseError("Provider response exceeded the configured size limit")
        body = bytearray()
        for chunk in response.iter_bytes():
            if len(body) + len(chunk) > byte_limit:
                raise ProviderResponseError("Provider response exceeded the configured size limit")
            body.extend(chunk)
    return _parse_provider_json(bytes(body))


def provider_message_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderResponseError("Provider response had an invalid shape") from exc
    if not isinstance(content, str):
        raise ProviderResponseError("Provider response had an invalid shape")
    return content


class AIProvider(ABC):
    name: str

    @abstractmethod
    async def generate_svg(self, challenge: str, model_config: dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def score_guess(self, original: str, guess: str) -> dict[str, Any]:
        pass

    def score_guess_sync(self, original: str, guess: str) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.score_guess(original, guess))
        return local_component_score(original, guess)


class MockAIProvider(AIProvider):
    name = "mock"

    async def generate_svg(self, challenge: str, model_config: dict[str, Any]) -> str:
        return sanitize_svg(mock_svg(challenge, str(model_config["tier"])))

    async def score_guess(self, original: str, guess: str) -> dict[str, Any]:
        return local_component_score(original, guess)


class OpenRouterAIProvider(AIProvider):
    name = "openrouter"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for AI_PROVIDER=openrouter")

    async def generate_svg(self, challenge: str, model_config: dict[str, Any]) -> str:
        tier = str(model_config["tier"])
        payload: dict[str, Any] = {
            "model": model_config["model"],
            "messages": [{"role": "user", "content": build_svg_prompt(challenge, tier)}],
            "temperature": 0.7,
            "max_tokens": 5000,
        }
        if model_config.get("reasoning_effort"):
            payload["reasoning_effort"] = model_config["reasoning_effort"]

        async with httpx.AsyncClient(timeout=60) as client:
            response_payload = await request_json_bounded(
                client,
                "POST",
                OPENROUTER_URL,
                headers=openrouter_headers(self.api_key),
                json=payload,
            )
        raw_svg = provider_message_content(response_payload)
        sanitized = sanitize_svg(raw_svg)
        validate_generated_svg(sanitized, challenge)
        return sanitized

    async def score_guess(self, original: str, guess: str) -> dict[str, Any]:
        judge_model = os.getenv("OPENROUTER_JUDGE_MODEL")
        if not judge_model:
            return local_component_score(original, guess)
        payload = {
            "model": judge_model,
            "messages": [{"role": "user", "content": build_judge_prompt(original, guess)}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=35) as client:
            response_payload = await request_json_bounded(
                client,
                "POST",
                OPENROUTER_URL,
                headers=openrouter_headers(self.api_key),
                json=payload,
            )
        result = _parse_provider_json(provider_message_content(response_payload).encode("utf-8"))
        local = local_component_score(original, guess)
        return normalize_judge_result(result, fallback=local)

    def score_guess_sync(self, original: str, guess: str) -> dict[str, Any]:
        judge_model = os.getenv("OPENROUTER_JUDGE_MODEL")
        if not judge_model:
            return local_component_score(original, guess)
        payload = {
            "model": judge_model,
            "messages": [{"role": "user", "content": build_judge_prompt(original, guess)}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=35) as client:
            response_payload = request_json_bounded_sync(
                client,
                "POST",
                OPENROUTER_URL,
                headers=openrouter_headers(self.api_key),
                json=payload,
            )
        result = _parse_provider_json(provider_message_content(response_payload).encode("utf-8"))
        return normalize_judge_result(result, fallback=local_component_score(original, guess))


class LocalModelProvider(AIProvider):
    name = "local"

    def __init__(self) -> None:
        self.base_url = os.getenv("LOCAL_MODEL_BASE_URL", "").rstrip("/")
        self.model = os.getenv("LOCAL_MODEL_NAME", "")
        if not self.base_url or not self.model:
            raise RuntimeError("LOCAL_MODEL_BASE_URL and LOCAL_MODEL_NAME are required for AI_PROVIDER=local")

    async def generate_svg(self, challenge: str, model_config: dict[str, Any]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": build_svg_prompt(challenge, str(model_config["tier"]))}],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response_payload = await request_json_bounded(
                client,
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
            )
        content = provider_message_content(response_payload)
        sanitized = sanitize_svg(content)
        validate_generated_svg(sanitized, challenge)
        return sanitized

    async def score_guess(self, original: str, guess: str) -> dict[str, Any]:
        return local_component_score(original, guess)


def configured_provider_name() -> str:
    provider = os.getenv("AI_PROVIDER", "openrouter" if os.getenv("OPENROUTER_API_KEY") else "mock").strip().lower()
    if provider not in SUPPORTED_AI_PROVIDERS:
        raise AIConfigurationError("Unsupported AI provider configuration")
    return provider


def get_ai_provider() -> AIProvider:
    provider = configured_provider_name()
    if provider == "openrouter":
        return OpenRouterAIProvider()
    if provider == "local":
        return LocalModelProvider()
    return MockAIProvider()


def get_ai_status() -> dict[str, Any]:
    provider_name = configured_provider_name()
    return {
        "runtime_provider": provider_name,
        "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
        "local_model_configured": bool(os.getenv("LOCAL_MODEL_BASE_URL") and os.getenv("LOCAL_MODEL_NAME")),
        "mock_mode_notice": "Mock mode uses prompt-derived labels and placeholder shapes. It verifies game flow, not real drawing quality."
        if provider_name == "mock"
        else None,
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


async def generate_artist_svg(challenge: str, model_config: dict[str, Any]) -> str:
    return await get_ai_provider().generate_svg(challenge, model_config)


async def score_guess(original: str, guess: str) -> dict[str, Any]:
    return await get_ai_provider().score_guess(original, guess)


def openrouter_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("APP_PUBLIC_URL", "http://localhost:8081"),
        "X-Title": "AI Pictionary MVP",
    }


def normalize_judge_result(result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    score = int(result.get("score", fallback["score"]))
    return {
        "score": max(0, min(100, score)),
        "matched_parts": list(result.get("matched_parts") or fallback["matched_parts"]),
        "missed_parts": list(result.get("missed_parts") or fallback["missed_parts"]),
        "short_feedback": str(result.get("short_feedback") or fallback["short_feedback"]),
        "component_scores": result.get("component_scores") or fallback["component_scores"],
    }


def local_component_score(original: str, guess: str) -> dict[str, Any]:
    original_components = semantic_components(original)
    guess_components = semantic_components(guess)
    component_scores: dict[str, int] = {}
    matched_parts: list[str] = []
    missed_parts: list[str] = []

    weights = {"characters": 36, "action": 32, "setting": 16, "twist": 16}
    total = 0
    for component, weight in weights.items():
        original_set = set(original_components[component])
        guess_set = set(guess_components[component])
        if not original_set:
            component_scores[component] = weight
            total += weight
            continue
        overlap = original_set & guess_set
        ratio = len(overlap) / len(original_set)
        fuzzy = SequenceMatcher(None, " ".join(original_set), " ".join(guess_set)).ratio() if guess_set else 0
        score = round(weight * max(ratio, fuzzy * 0.72))
        component_scores[component] = score
        total += score
        matched_parts.extend(sorted(overlap))
        missed_parts.extend(sorted(original_set - guess_set))

    if total >= 82:
        feedback = "Strong guess. The main characters, action, and vibe are mostly there."
    elif total >= 55:
        feedback = "Close, but a few important pieces are still missing."
    else:
        feedback = "Different idea. Focus on the main characters, action, and setting."

    return {
        "score": max(0, min(100, total)),
        "matched_parts": matched_parts[:10],
        "missed_parts": missed_parts[:10],
        "short_feedback": feedback,
        "component_scores": component_scores,
    }


def semantic_components(text: str) -> dict[str, list[str]]:
    words = ordered_keywords(text)
    actions = [word for word in words if word in ACTION_WORDS or word.endswith("ing")]
    settings = [word for word in words if word in SETTING_WORDS]
    twist = [word for word in words if word in MOOD_WORDS]
    characters = [word for word in words if word not in set(actions + settings + twist)]
    return {
        "characters": characters[:5],
        "action": actions[:3],
        "setting": settings[:3],
        "twist": twist[:3],
    }


def keywords(text: str) -> set[str]:
    return set(ordered_keywords(text))


def ordered_keywords(text: str) -> list[str]:
    seen = set()
    ordered = []
    for word in re.findall(r"[a-zA-Z0-9']+", text.lower()):
        if len(word) <= 2 or word in STOPWORDS or word in seen:
            continue
        seen.add(word)
        ordered.append(word)
    return ordered


def validate_generated_svg(svg_text: str, challenge: str) -> None:
    lower_svg = svg_text.lower()
    normalized_prompt = " ".join(ordered_keywords(challenge))
    text_content = " ".join(re.findall(r">([^<>]{4,})<", svg_text)).lower()
    if normalized_prompt and normalized_prompt in " ".join(ordered_keywords(text_content)):
        raise ValueError("Generated SVG appears to reveal the full prompt as text")
    shape_count = len(re.findall(r"<(path|circle|rect|ellipse|polygon|polyline|line)\b", lower_svg))
    meaningful_size = len(svg_text.encode("utf-8"))
    if shape_count < 5 or meaningful_size < 900:
        raise ValueError("Generated SVG is too empty or generic")


def mock_svg(challenge: str, tier: str) -> str:
    components = semantic_components(challenge)
    character_labels = [html.escape(word.title()) for word in components["characters"][:2]]
    action_label = html.escape((components["action"][0] if components["action"] else "doing").title())
    setting_label = html.escape((components["setting"][0] if components["setting"] else "scene").title())
    twist_label = html.escape((components["twist"][0] if components["twist"] else tier).title())
    label_one = character_labels[0] if character_labels else "Main"
    label_two = character_labels[1] if len(character_labels) > 1 else "Object"
    seed = sum(ord(char) for char in challenge + tier)
    x_offset = seed % 120
    wobble = 24 if tier == "confusing" else 10 if tier == "balanced" else 0
    palette = {
        "confusing": ("#FFE066", "#FF6B5F", "#1F2937"),
        "balanced": ("#70D6C9", "#4E79FF", "#172554"),
        "literal": ("#F8FAFC", "#53C2A8", "#111827"),
    }.get(tier, ("#FFE066", "#FF6B5F", "#1F2937"))

    return f"""
<svg viewBox="0 0 1024 1024" width="1024" height="1024" role="img" aria-label="AI drawing clue">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{palette[0]}"/>
      <stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="1024" height="1024" fill="url(#bg)"/>
  <ellipse cx="512" cy="748" rx="350" ry="82" fill="#FFFFFF" opacity="0.58"/>
  <circle cx="{250 + x_offset}" cy="{270 + wobble}" r="96" fill="#FFFFFF" opacity="0.92"/>
  <circle cx="{250 + x_offset}" cy="{246 + wobble}" r="28" fill="{palette[1]}" opacity="0.88"/>
  <rect x="{520 - x_offset // 3}" y="{210 + wobble}" width="210" height="150" rx="32" fill="#FFFFFF" opacity="0.92"/>
  <circle cx="{625 - x_offset // 3}" cy="{236 + wobble}" r="28" fill="{palette[1]}" opacity="0.88"/>
  <path d="M210 650 C320 500, 450 790, 575 620 S795 585, 840 725" fill="none" stroke="{palette[2]}" stroke-width="30" stroke-linecap="round"/>
  <path d="M320 410 C410 500, 500 500, 600 410" fill="none" stroke="{palette[1]}" stroke-width="24" stroke-linecap="round"/>
  <polygon points="488,486 606,420 725,486 725,650 488,650" fill="{palette[1]}" opacity="0.88"/>
  <rect x="530" y="542" width="154" height="108" rx="12" fill="#FFFFFF"/>
  <line x1="552" y1="568" x2="552" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <line x1="590" y1="568" x2="590" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <line x1="628" y1="568" x2="628" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <line x1="666" y1="568" x2="666" y2="640" stroke="{palette[2]}" stroke-width="10"/>
  <text x="512" y="122" font-size="56" font-family="Arial" font-weight="700" text-anchor="middle" fill="{palette[2]}">{action_label}</text>
  <text x="268" y="292" font-size="38" font-family="Arial" font-weight="700" text-anchor="middle" fill="{palette[2]}">{label_two}</text>
  <text x="625" y="300" font-size="36" font-family="Arial" font-weight="700" text-anchor="middle" fill="{palette[2]}">{label_one}</text>
  <text x="512" y="838" font-size="34" font-family="Arial" font-weight="700" text-anchor="middle" fill="{palette[2]}">{setting_label}</text>
  <text x="512" y="888" font-size="28" font-family="Arial" text-anchor="middle" fill="{palette[2]}">mock {tier}: {twist_label}</text>
</svg>
"""
