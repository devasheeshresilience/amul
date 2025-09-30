"""Persistent state management for stock statuses and user subscriptions.

Provides JSON file backed dictionaries with atomic-ish write (write temp then replace).

Files:
- stock_state.json : product_id -> last_in_stock(bool)
- user_state.json  : (shared with bot) structure defined there

This module focuses only on stock state persistence.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

STOCK_STATE_FILE = Path("stock_state.json")


class PersistentStockState:
    def __init__(self, path: Path = STOCK_STATE_FILE) -> None:
        self.path = path
        self._data: Dict[str, bool] = {}
        self._load()

    def _load(self) -> None:
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text("utf-8"))
            except Exception as e:  # pragma: no cover
                logger.warning("Could not load stock state: %s", e)
                self._data = {}

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception as e:  # pragma: no cover
            logger.error("Failed saving stock state: %s", e)

    def get(self, product_id: str) -> bool | None:
        return self._data.get(product_id)

    def set(self, product_id: str, in_stock: bool) -> None:
        self._data[product_id] = in_stock
        self._save()

    def status_changed(self, product_id: str, new: bool) -> tuple[bool, bool | None]:
        prev = self.get(product_id)
        self.set(product_id, new)
        if prev is None:
            return (new, None)
        if prev != new:
            return (True, prev)
        return (False, prev)

__all__ = ["PersistentStockState"]
