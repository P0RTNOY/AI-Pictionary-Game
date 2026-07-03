from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import EXPO_ACCESS_TOKEN, NOTIFICATION_PROVIDER
from app.orm_models import DeviceToken, NotificationAttempt


logger = logging.getLogger("ai_pictionary.notifications")
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


@dataclass
class NotificationMessage:
    user_id: str
    title: str
    body: str
    data: dict[str, Any]


NOTIFICATION_OUTBOX: list[NotificationMessage] = []


class NotificationProvider(Protocol):
    name: str

    def send(self, token: str, title: str, body: str, data: dict[str, Any]) -> dict[str, Any]:
        pass


class MockNotificationProvider:
    name = "mock"

    def send(self, token: str, title: str, body: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "mock": True}


class ExpoPushNotificationProvider:
    name = "expo"

    def send(self, token: str, title: str, body: str, data: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if EXPO_ACCESS_TOKEN:
            headers["Authorization"] = f"Bearer {EXPO_ACCESS_TOKEN}"
        payload = {"to": token, "title": title, "body": body, "data": data, "sound": "default"}
        with httpx.Client(timeout=10) as client:
            response = client.post(EXPO_PUSH_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()


def get_notification_provider() -> NotificationProvider:
    if NOTIFICATION_PROVIDER == "expo":
        return ExpoPushNotificationProvider()
    return MockNotificationProvider()


def notify_user(db: Session, user_id: str, title: str, body: str, data: dict[str, Any]) -> None:
    NOTIFICATION_OUTBOX.append(NotificationMessage(user_id=user_id, title=title, body=body, data=data))
    provider = get_notification_provider()
    tokens = (
        db.execute(select(DeviceToken).where(DeviceToken.user_id == user_id, DeviceToken.status == "active"))
        .scalars()
        .all()
    )
    if not tokens:
        logger.info("notification.no_tokens", extra={"user_id": user_id, "title": title})
    for token in tokens:
        attempt = NotificationAttempt(
            id=str(uuid.uuid4()),
            user_id=user_id,
            device_token_id=token.id,
            provider=provider.name,
            title=title,
            body=body,
            payload_json=json.dumps(data),
            status="pending",
        )
        db.add(attempt)
        db.flush()
        try:
            logger.info("notification.send_attempt", extra={"user_id": user_id, "provider": provider.name})
            result = provider.send(token.token, title, body, data)
            attempt.status = "sent"
            attempt.response_json = json.dumps(result)
        except Exception as exc:
            attempt.status = "failed"
            attempt.error_message = str(exc)
            logger.warning("notification.send_failed", extra={"user_id": user_id, "error": str(exc)})
