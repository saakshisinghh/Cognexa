"""
apps/api/models/conversation.py

Phase 4 ORM model: ConversationSession
Compatible with the existing project which uses STRING primary keys.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base

_MAX_RECENT_MESSAGES = 5


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    # ------------------------------------------------------------------
    # Primary Key (STRING, same as User/Asset/Document)
    # ------------------------------------------------------------------

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ------------------------------------------------------------------
    # Foreign Keys (STRING)
    # ------------------------------------------------------------------

    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Phase 4 no longer references plants table
    plant_id: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    pinned_asset_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    pinned_asset_tag: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # Conversation State
    # ------------------------------------------------------------------

    recent_messages_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    @property
    def recent_messages(self) -> list[dict]:
        try:
            return json.loads(self.recent_messages_json or "[]")
        except Exception:
            return []

    def append_message(self, role: str, content: str) -> None:
        messages = self.recent_messages

        messages.append(
            {
                "role": role,
                "content": content,
            }
        )

        if len(messages) > (_MAX_RECENT_MESSAGES * 2):
            messages = messages[-(_MAX_RECENT_MESSAGES * 2):]

        self.recent_messages_json = json.dumps(messages)
        self.message_count += 1
        self.last_active_at = datetime.now(timezone.utc)

    def set_title_from_query(self, query: str) -> None:
        if not self.title:
            self.title = query[:80].strip()

    def pin_asset(
        self,
        asset_id: Optional[str],
        asset_tag: Optional[str],
    ) -> None:
        self.pinned_asset_id = asset_id
        self.pinned_asset_tag = asset_tag