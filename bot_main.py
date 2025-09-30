"""Interactive Telegram bot entrypoint.

Behavior:
- /start : Greets user and asks for 6-digit pincode.
- User sends pincode (4-6 digits accepted for flexibility) -> bot saves it and responds with currently in-stock products for that pincode.
- /check : Re-runs availability check using previously stored pincode.
- /subscribe : Enable periodic notifications (future extension placeholder).
- /unsubscribe : Disable periodic notifications.

Storage:
- Simple JSON file `user_state.json` mapping chat_id -> {"pincode": str, "subscribed": bool}
  (In-memory + persisted after each change.)

Pincode filtering:
- Placeholder logic: currently returns all in-stock products (no geolocation mapping implemented).
  Extend `product_available_for_pincode` to apply real filtering rules once API supports querying by pincode or location mapping is known.

Run:
  python bot_main.py

Environment variables:
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (CHAT_ID only needed if you want to send a broadcast outside conversation)
- PAYLOAD_FILE (optional) see main.py
- LOG_LEVEL (optional)

NOTE: This runs a long-lived async Application unlike the polling worker in main.py.

"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from stock_checker import parse_products
from fetcher import fetch_payload

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot")

STATE_FILE = Path("user_state.json")

# ---------- Data Loading (reuse logic similar to main) ----------
SAMPLE_PAYLOAD: Dict[str, Any] = {"data": []}

PINCODE_MAP_FILE = Path("pincode_products.json")  # optional mapping file structure: {"122001": ["product_id1", ...]}

_PINCODE_CACHE: Dict[str, set[str]] | None = None


def _load_pincode_mapping() -> Dict[str, set[str]]:
    global _PINCODE_CACHE
    if _PINCODE_CACHE is not None:
        return _PINCODE_CACHE
    if PINCODE_MAP_FILE.is_file():
        try:
            raw = json.loads(PINCODE_MAP_FILE.read_text("utf-8"))
            _PINCODE_CACHE = {k: set(v) for k, v in raw.items() if isinstance(v, list)}
            return _PINCODE_CACHE
        except Exception as e:  # pragma: no cover
            logger.warning("Failed to load pincode mapping: %s", e)
    _PINCODE_CACHE = {}
    return _PINCODE_CACHE


# ---------- State Persistence ----------
class UserStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._state: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.is_file():
            try:
                self._state = json.loads(self.path.read_text("utf-8"))
            except Exception as e:  # pragma: no cover
                logger.warning("Could not load state file: %s", e)
                self._state = {}

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except Exception as e:  # pragma: no cover
            logger.error("Could not save state: %s", e)

    def set_pincode(self, chat_id: int, pincode: str) -> None:
        entry = self._state.setdefault(str(chat_id), {"pincode": None, "subscribed": False})
        entry["pincode"] = pincode
        self._save()

    def get_pincode(self, chat_id: int) -> str | None:
        entry = self._state.get(str(chat_id))
        return entry.get("pincode") if entry else None

    def set_subscription(self, chat_id: int, subscribed: bool) -> None:
        entry = self._state.setdefault(str(chat_id), {"pincode": None, "subscribed": False})
        entry["subscribed"] = subscribed
        self._save()

    def is_subscribed(self, chat_id: int) -> bool:
        entry = self._state.get(str(chat_id))
        return bool(entry and entry.get("subscribed"))

    def all_subscribed(self) -> Dict[int, str]:
        result: Dict[int, str] = {}
        for cid, data in self._state.items():
            if data.get("subscribed") and data.get("pincode"):
                result[int(cid)] = data["pincode"]
        return result


store = UserStateStore(STATE_FILE)

# ---------- Business Logic ----------
PINCODE_REGEX = re.compile(r"^\d{4,6}$")


def product_available_for_pincode(product_raw: Dict[str, Any], pincode: str) -> bool:
    """Filtering using optional pincode mapping file.

    Behavior:
    - If mapping file present and contains pincode -> restrict to product IDs listed.
    - If no mapping or pincode not in mapping, allow all (fallback True).
    """
    mapping = _load_pincode_mapping()
    if not mapping or pincode not in mapping:
        return True
    pid = str(product_raw.get("_id"))
    return pid in mapping[pincode]


def format_products_list(products) -> str:
    if not products:
        return "No products are currently in stock for your pincode."
    lines = ["In-stock products:"]
    for p in products[:30]:  # safety cap
        qty = p.inventory_quantity if p.inventory_quantity is not None else "?"
        lines.append(f"• {p.name} (qty: {qty})")
    if len(products) > 30:
        lines.append(f"…and {len(products)-30} more")
    return "\n".join(lines)


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! Send me your pincode (4–6 digits) and I'll list available products."
    )


async def handle_pincode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    text = (update.message.text or "").strip()
    if not PINCODE_REGEX.fullmatch(text):
        await update.message.reply_text("Please send a valid pincode (4–6 digits).")
        return
    chat_id = update.effective_chat.id
    store.set_pincode(chat_id, text)
    await update.message.reply_text(f"Pincode set to {text}. Checking availability…")
    await send_availability(chat_id, context)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await send_availability(chat_id, context)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not store.get_pincode(chat_id):
        await update.message.reply_text("Set your pincode first by sending it.")
        return
    store.set_subscription(chat_id, True)
    await update.message.reply_text("Subscribed to periodic updates (every 10 minutes). Use /unsubscribe to stop.")


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    store.set_subscription(chat_id, False)
    await update.message.reply_text("Unsubscribed from periodic updates.")


async def periodic_job(context: ContextTypes.DEFAULT_TYPE) -> None:  # pragma: no cover (time-based)
    for chat_id, pincode in store.all_subscribed().items():
        await send_availability(chat_id, context, silent=True)


async def send_availability(chat_id: int, context: ContextTypes.DEFAULT_TYPE, silent: bool = False) -> None:
    pincode = store.get_pincode(chat_id)
    if not pincode:
        if not silent:
            await context.bot.send_message(chat_id, "No pincode set. Send your pincode to begin.")
        return
    payload = fetch_payload()
    products = parse_products(payload)
    filtered = [p for p in products if p.in_stock and product_available_for_pincode(p.raw, pincode)]
    message = format_products_list(filtered)
    if silent and not filtered:
        # Optionally suppress empty updates in silent mode; here we still send.
        pass
    await context.bot.send_message(chat_id, message)


# ---------- App Runner ----------
async def on_startup(app):  # pragma: no cover
    logger.info("Bot started. Registered handlers for start/pincode/check/subscribe.")


def main() -> None:  # pragma: no cover
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))

    # Any text that matches pincode format
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pincode))

    # Periodic job every 10 minutes
    app.job_queue.run_repeating(periodic_job, interval=600, first=600)

    app.run_polling(stop_signals=None)


if __name__ == "__main__":
    main()
