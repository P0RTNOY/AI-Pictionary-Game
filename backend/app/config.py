from __future__ import annotations

import os


LOCAL_ENVS = {"local", "dev", "development", "test"}


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_local_env(env: str) -> bool:
    return env.lower() in LOCAL_ENVS


ENV = os.getenv("ENV", "development").lower()
DEBUG = parse_bool(os.getenv("DEBUG"), default=is_local_env(ENV))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_pictionary.db")
AUTO_CREATE_TABLES = parse_bool(os.getenv("AUTO_CREATE_TABLES"), default=is_local_env(ENV))
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:8081,http://127.0.0.1:8081").split(",")
    if origin.strip()
]
if is_local_env(ENV) and "*" not in CORS_ALLOW_ORIGINS:
    CORS_ALLOW_ORIGINS.append("*")

NOTIFICATION_PROVIDER = os.getenv("NOTIFICATION_PROVIDER", "mock").lower()
EXPO_ACCESS_TOKEN = os.getenv("EXPO_ACCESS_TOKEN", "")
