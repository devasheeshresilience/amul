"""Entrypoint for stock monitoring backend.

Features:
- Periodically (default 60s) loads a JSON payload (simulated file or inline sample)
- Parses product stock status using stock_checker module
- Detects newly in-stock products
- Sends Telegram notifications via notifier module

Configuration via environment variables:
- POLL_INTERVAL (seconds, default 60)
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- PAYLOAD_FILE (optional path to a JSON file containing the latest API response)

On Railway you can set these in the project variables UI.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any

from stock_checker import parse_products, detect_in_stock_transitions, StockState
from notifier import TelegramNotifier

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")

# A fallback sample payload (trimmed). Replace with real API response or a file path.
SAMPLE_PAYLOAD: Dict[str, Any] = {
    "data": [
        {
            "_id": "6636020d5c0420e92d79ebdd",
            "name": "Amul High Protein Paneer, 400 g | Pack of 2",
            "available": 1,
            "inventory_quantity": 1079,
        }
    ]
}


def load_payload() -> Dict[str, Any]:
    path = os.getenv("PAYLOAD_FILE")
    if path:
        p = Path(path)
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:  # pragma: no cover - file errors
                logger.error("Failed to read payload file %s: %s", path, e)
    return SAMPLE_PAYLOAD


def main() -> None:
    interval = int(os.getenv("POLL_INTERVAL", "60"))
    notifier = TelegramNotifier()
    state = StockState()

    logger.info("Starting stock monitor loop (interval=%ss)", interval)
    while True:
        payload = load_payload()
        products = parse_products(payload)
        newly_available = detect_in_stock_transitions(products, state)

        for p in newly_available:
            msg = (
                f"<b>{p.name}</b> just came <b>IN STOCK</b>!\n"
                f"Inventory: {p.inventory_quantity if p.inventory_quantity is not None else 'unknown'}"
            )
            notifier.send(msg)

        logger.debug(
            "Cycle complete: products=%d newly_available=%d", len(products), len(newly_available)
        )
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover
    main()
