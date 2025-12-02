"""Configuration management for the bot."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _parse_admin_chat_id(raw_value: str | None) -> Optional[int]:
    """Parse ADMIN_CHAT_ID from environment safely."""
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value != 0 else None


@dataclass(frozen=True)
class Settings:
    """Bot settings loaded from environment variables."""

    bot_token: str
    admin_chat_id: Optional[int]
    leads_file: str = "leads.jsonl"

    @classmethod
    def load(cls) -> "Settings":
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise RuntimeError("Не найден BOT_TOKEN в переменных окружения")

        admin_chat_id = _parse_admin_chat_id(os.getenv("ADMIN_CHAT_ID"))
        return cls(bot_token=bot_token, admin_chat_id=admin_chat_id)
