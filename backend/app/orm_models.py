from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    avatar_emoji: Mapped[str] = mapped_column(String(16), default="🙂", nullable=False)
    avatar_color: Mapped[str] = mapped_column(String(16), default="#F5C84C", nullable=False)
    auth_provider: Mapped[Optional[str]] = mapped_column(String(40))
    auth_subject: Mapped[Optional[str]] = mapped_column(String(160))
    session_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)


class Game(TimestampMixin, Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    player_1_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    player_2_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    current_turn_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    rounds: Mapped[list["Round"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    events: Mapped[list["GameEvent"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class WebSocketTicket(Base):
    __tablename__ = "websocket_tickets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    game_id: Mapped[str] = mapped_column(String(64), ForeignKey("games.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class GameInvite(TimestampMixin, Base):
    __tablename__ = "game_invites"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    creator_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    game_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("games.id"))
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class DeviceToken(TimestampMixin, Base):
    __tablename__ = "device_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="expo", nullable=False)
    token: Mapped[str] = mapped_column(String(500), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    device_token_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("device_tokens.id"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    response_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Round(TimestampMixin, Base):
    __tablename__ = "rounds"
    __table_args__ = (
        Index(
            "uq_rounds_one_active_per_game",
            "game_id",
            unique=True,
            sqlite_where=text("status IN ('generating', 'ready_to_guess')"),
            postgresql_where=text("status IN ('generating', 'ready_to_guess')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(64), ForeignKey("games.id"), nullable=False)
    creator_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    guesser_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="generating", nullable=False)
    clue_reveal_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    game: Mapped[Game] = relationship(back_populates="rounds")
    generated_svgs: Mapped[list["GeneratedSvg"]] = relationship(
        back_populates="round", cascade="all, delete-orphan", order_by="GeneratedSvg.sort_order"
    )
    guesses: Mapped[list["Guess"]] = relationship(back_populates="round", cascade="all, delete-orphan")


class GeneratedSvg(TimestampMixin, Base):
    __tablename__ = "generated_svgs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    round_id: Mapped[str] = mapped_column(String(64), ForeignKey("rounds.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    model_tier: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_used: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    svg_text: Mapped[Optional[str]] = mapped_column(Text)
    generation_time_seconds: Mapped[Optional[float]]
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    round: Mapped[Round] = relationship(back_populates="generated_svgs")


class Guess(TimestampMixin, Base):
    __tablename__ = "guesses"
    __table_args__ = (Index("uq_guesses_round_id", "round_id", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    round_id: Mapped[str] = mapped_column(String(64), ForeignKey("rounds.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    guess_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    judge_result_json: Mapped[str] = mapped_column(Text, nullable=False)
    component_scores_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    clue_count_used: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    round: Mapped[Round] = relationship(back_populates="guesses")


class GenerationAdmissionGate(Base):
    __tablename__ = "generation_admission_gate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GameEvent(Base):
    __tablename__ = "game_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(64), ForeignKey("games.id"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    game: Mapped[Game] = relationship(back_populates="events")
