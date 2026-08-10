from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import (
    EXPO_ACCESS_TOKEN,
    NOTIFICATION_FANOUT_LIMIT,
    NOTIFICATION_OUTBOX_LIMIT,
    NOTIFICATION_PROVIDER,
)
from app.orm_models import DeviceToken, NotificationAttempt


logger = logging.getLogger("ai_pictionary.notifications")
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


@dataclass
class NotificationMessage:
    user_id: str
    title: str
    body: str
    data: dict[str, Any]


@dataclass(frozen=True)
class NotificationDispatch:
    attempt_id: str
    token: str
    title: str
    body: str
    data: dict[str, Any]


NOTIFICATION_OUTBOX: list[NotificationMessage] = []
_OUTBOX_LOCK = Lock()


def append_notification_message(message: NotificationMessage) -> None:
    with _OUTBOX_LOCK:
        NOTIFICATION_OUTBOX.append(message)
        if len(NOTIFICATION_OUTBOX) > NOTIFICATION_OUTBOX_LIMIT:
            del NOTIFICATION_OUTBOX[: len(NOTIFICATION_OUTBOX) - NOTIFICATION_OUTBOX_LIMIT]


def notification_outbox_snapshot() -> list[NotificationMessage]:
    with _OUTBOX_LOCK:
        return list(NOTIFICATION_OUTBOX)


def clear_notification_outbox() -> None:
    with _OUTBOX_LOCK:
        NOTIFICATION_OUTBOX.clear()


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
    if NOTIFICATION_PROVIDER == "mock":
        return MockNotificationProvider()
    raise ValueError("NOTIFICATION_PROVIDER must be one of: expo, mock")


def notify_user(
    db: Session,
    user_id: str,
    title: str,
    body: str,
    data: dict[str, Any],
) -> list[NotificationDispatch]:
    append_notification_message(NotificationMessage(user_id=user_id, title=title, body=body, data=data))
    provider = get_notification_provider()
    tokens = (
        db.execute(
            select(DeviceToken)
            .where(DeviceToken.user_id == user_id, DeviceToken.status == "active")
            .order_by(DeviceToken.updated_at.desc(), DeviceToken.id.desc())
            .limit(NOTIFICATION_FANOUT_LIMIT)
        )
        .scalars()
        .all()
    )
    if not tokens:
        logger.info("notification.no_tokens", extra={"user_id": user_id, "title": title})
    dispatches: list[NotificationDispatch] = []
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
        dispatches.append(
            NotificationDispatch(
                attempt_id=attempt.id,
                token=token.token,
                title=title,
                body=body,
                data=data,
            )
        )
    return dispatches


def deliver_notifications(db: Session, dispatches: list[NotificationDispatch]) -> None:
    """Deliver already-committed attempts and persist only bounded, safe outcomes."""
    if not dispatches:
        return
    try:
        provider = get_notification_provider()
        for dispatch in dispatches:
            attempt = db.get(NotificationAttempt, dispatch.attempt_id)
            if not attempt or attempt.status != "pending":
                continue
            try:
                logger.info(
                    "notification.send_attempt",
                    extra={"user_id": attempt.user_id, "provider": provider.name},
                )
                result = provider.send(
                    dispatch.token,
                    dispatch.title,
                    dispatch.body,
                    dispatch.data,
                )
                attempt.status = "sent"
                attempt.response_json = json.dumps(result, default=str)[:4096]
            except Exception as exc:
                attempt.status = "failed"
                attempt.error_message = "Notification delivery failed"
                logger.warning(
                    "notification.send_failed",
                    extra={
                        "user_id": attempt.user_id,
                        "exception_type": f"{exc.__class__.__module__}.{exc.__class__.__name__}",
                    },
                )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "notification.delivery_bookkeeping_failed",
            extra={"exception_type": f"{exc.__class__.__module__}.{exc.__class__.__name__}"},
        )
