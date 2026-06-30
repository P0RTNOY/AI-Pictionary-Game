from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx
from dotenv import load_dotenv


load_dotenv()


@dataclass
class CheckResult:
    name: str
    configured: bool
    ok: bool
    detail: str


async def main() -> None:
    checks: list[tuple[str, str, Callable[[str], Awaitable[CheckResult]]]] = [
        ("OpenRouter", "OPENROUTER_API_KEY", check_openrouter),
        ("OpenAI", "OPENAI_API_KEY", check_openai),
        ("Anthropic", "ANTHROPIC_API_KEY", check_anthropic),
        ("Google", "GOOGLE_API_KEY", check_google),
        ("DeepSeek", "DEEPSEEK_API_KEY", check_deepseek),
        ("Groq", "GROQ_API_KEY", check_groq),
        ("xAI/Grok", "GROK_API_KEY", check_xai),
    ]
    results = await asyncio.gather(*(run_check(name, env_name, checker) for name, env_name, checker in checks))

    print("Provider key check")
    print("------------------")
    for result in results:
        if not result.configured:
            marker = "missing"
        elif result.ok:
            marker = "ok"
        else:
            marker = "failed"
        print(f"{result.name:12} {marker:8} {result.detail}")


async def run_check(name: str, env_name: str, checker: Callable[[str], Awaitable[CheckResult]]) -> CheckResult:
    key = os.getenv(env_name)
    if not key:
        return CheckResult(name=name, configured=False, ok=False, detail=f"{env_name} is not set")
    try:
        return await checker(key)
    except Exception as exc:
        return CheckResult(name=name, configured=True, ok=False, detail=f"{type(exc).__name__}: {exc}")


async def check_openrouter(key: str) -> CheckResult:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})
    return result_from_response("OpenRouter", response)


async def check_openai(key: str) -> CheckResult:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
    return result_from_response("OpenAI", response)


async def check_anthropic(key: str) -> CheckResult:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
    return result_from_response("Anthropic", response)


async def check_google(key: str) -> CheckResult:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key})
    return result_from_response("Google", response)


async def check_deepseek(key: str) -> CheckResult:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {key}"})
    return result_from_response("DeepSeek", response)


async def check_groq(key: str) -> CheckResult:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"})
    return result_from_response("Groq", response)


async def check_xai(key: str) -> CheckResult:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.x.ai/v1/models", headers={"Authorization": f"Bearer {key}"})
    return result_from_response("xAI/Grok", response)


def result_from_response(name: str, response: httpx.Response) -> CheckResult:
    if 200 <= response.status_code < 300:
        return CheckResult(name=name, configured=True, ok=True, detail=f"HTTP {response.status_code}")
    body = response.text.replace("\n", " ")[:120]
    return CheckResult(name=name, configured=True, ok=False, detail=f"HTTP {response.status_code}: {body}")


if __name__ == "__main__":
    asyncio.run(main())
