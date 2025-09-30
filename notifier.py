"""Telegram notification helper.

Uses python-telegram-bot >= 20 (async based).
We keep a simple abstraction so main loop can call a synchronous wrapper.

Environment variables expected:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID (can be a channel ID or user chat id)

If these are missing, the notifier will log a warning and skip sending.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not set; notifications disabled.")
        if not self.chat_id:
            logger.warning("TELEGRAM_CHAT_ID not set; notifications disabled.")
        self._bot: Bot | None = Bot(self.token) if self.token else None

    async def _send_async(self, text: str) -> None:
        if not self._bot or not self.chat_id:
            logger.debug("Notifier inactive; skipping send: %s", text)
            return
        try:
            await self._bot.send_message(chat_id=self.chat_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            logger.info("Sent Telegram alert: %s", text)
        except Exception as e:  # pragma: no cover - network/telegram errors
            logger.error("Error sending Telegram message: %s", e)

    def send(self, text: str) -> None:
        """Public sync wrapper. Safe to call from sync code."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If already in an async context add a task
            asyncio.create_task(self._send_async(text))
        else:
            loop.run_until_complete(self._send_async(text))


__all__ = ["TelegramNotifier"]
