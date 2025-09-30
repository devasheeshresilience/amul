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
import random
from pathlib import Path
from typing import Dict, Any

from stock_checker import parse_products, detect_in_stock_transitions, StockState
from notifier import TelegramNotifier
from fetcher import fetch_payload
from persistent_state import PersistentStockState

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")

# A fallback sample payload (trimmed). Replace with real API response or a file path.
SAMPLE_PAYLOAD: Dict[str, Any] = {"data": []}  # retained for reference; fetcher handles fallback


def main() -> None:
    interval = int(os.getenv("POLL_INTERVAL", "60"))
    notifier = TelegramNotifier()
    # In-memory state (per run) plus persistent state across restarts
    volatile_state = StockState()
    persistent_state = PersistentStockState()

    logger.info("Starting stock monitor loop (interval=%ss)", interval)
    while True:
        payload = fetch_payload()
        products = parse_products(payload)
        newly_available = detect_in_stock_transitions(products, volatile_state)

        # Persist states and only alert on transitions per persistent store as well
        final_alerts = []
        for p in newly_available:
            changed_persist, prev = persistent_state.status_changed(p.product_id, p.in_stock)
            if changed_persist and p.in_stock:
                final_alerts.append(p)

        for p in final_alerts:
            msg = (
                f"<b>{p.name}</b> just came <b>IN STOCK</b>!"\
                f"\nInventory: {p.inventory_quantity if p.inventory_quantity is not None else 'unknown'}"\
                f"\nProduct ID: {p.product_id}"
            )
            notifier.send(msg)

        logger.debug(
            "Cycle complete: products=%d in_memory_new=%d persistent_alerts=%d", len(products), len(newly_available), len(final_alerts)
        )
        # Add small jitter to avoid thundering herd if multiple instances
        jitter = random.uniform(0, min(5, interval * 0.2))
        time.sleep(interval + jitter)


if __name__ == "__main__":  # pragma: no cover
    main()
