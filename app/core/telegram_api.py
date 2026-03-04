"""
Telegram Bot API helpers for sending messages.

Used by:
- daily_digest.py (WF02) — send digest to group chats
- deadline_extractor.py (WF06) — send task notifications
- bot error alerts

Note: The Telegram BOT (WF04) uses python-telegram-bot library
for command handling. This module provides low-level send helpers
for scheduled tasks that just need to push messages.
"""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.logger import get_logger

log = get_logger("telegram")

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096


class TelegramSender:
    """Low-level Telegram message sender for scheduled tasks."""

    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token
        self._client = httpx.Client(timeout=30.0)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def send_message(
        self,
        chat_id: str | int,
        text: str,
        parse_mode: str = "HTML",
        disable_preview: bool = True,
    ) -> int | None:
        """
        Send a single message to a Telegram chat.

        Returns message_id on success, None on failure.
        """
        url = f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        response = self._client.post(url, json=payload)
        data = response.json()

        if data.get("ok"):
            msg_id = data["result"]["message_id"]
            log.info("telegram_sent", chat_id=chat_id, message_id=msg_id, chars=len(text))
            return msg_id

        log.error("telegram_send_failed", chat_id=chat_id, error=data.get("description"))
        return None

    def send_message_chunked(
        self,
        chat_id: str | int,
        text: str,
        parse_mode: str = "HTML",
    ) -> list[int]:
        """
        Send a long message, splitting into chunks if > 4096 chars.

        Returns list of message_ids sent.
        """
        if len(text) <= MAX_MESSAGE_LENGTH:
            msg_id = self.send_message(chat_id, text, parse_mode)
            return [msg_id] if msg_id else []

        # Split at last newline before limit
        message_ids: list[int] = []
        remaining = text
        while remaining:
            if len(remaining) <= MAX_MESSAGE_LENGTH:
                chunk = remaining
                remaining = ""
            else:
                # Find a good split point
                split_at = remaining[:MAX_MESSAGE_LENGTH].rfind("\n")
                if split_at < MAX_MESSAGE_LENGTH // 2:
                    split_at = MAX_MESSAGE_LENGTH - 1
                chunk = remaining[:split_at]
                remaining = remaining[split_at:].lstrip("\n")

            msg_id = self.send_message(chat_id, chunk, parse_mode)
            if msg_id:
                message_ids.append(msg_id)

        return message_ids

    def close(self) -> None:
        self._client.close()
