"""Stock checking logic.

This module parses the Amul (or similar) product list JSON response and determines
whether products are in stock. It also tracks previous stock states to avoid
sending duplicate alerts.

The JSON structure (simplified) expected:
{
    "data": [
        {
            "_id": "product_id",
            "name": "Product Name",
            "available": 1,                # 1 / 0 (sometimes string) indicates published availability
            "inventory_quantity": 1079,     # Integer > 0 when in stock
            ... other fields ...
        }
    ]
}

Heuristics for in-stock:
- If inventory_quantity (int) > 0 AND available flag in (1, "1", True), then in stock.
- Otherwise, out of stock.

You can adjust the heuristic if the real API differs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProductStockInfo:
    product_id: str
    name: str
    in_stock: bool
    inventory_quantity: int | None
    raw: Dict[str, Any]

    def human_status(self) -> str:
        return "IN STOCK" if self.in_stock else "OUT OF STOCK"


class StockState:
    """Tracks last known stock status per product to suppress duplicate alerts."""

    def __init__(self) -> None:
        self._last_status: Dict[str, bool] = {}

    def status_changed(self, info: ProductStockInfo) -> Tuple[bool, bool | None]:
        """Return (changed, previous_status).

        changed is True only when we have a previous value and the new value differs,
        OR when it's the first time and product is in stock (so we can choose to alert on first sighting).
        For this application we alert only on transition False -> True.
        """
        prev = self._last_status.get(info.product_id)
        self._last_status[info.product_id] = info.in_stock

        if prev is None:
            # First observation: only treat as change if now in stock (optional policy)
            return (info.in_stock, None)
        if prev != info.in_stock:
            return (True, prev)
        return (False, prev)


def parse_products(payload: Dict[str, Any]) -> List[ProductStockInfo]:
    """Parse the JSON payload and return list of ProductStockInfo objects.

    Safely handles missing keys.
    """
    data = payload.get("data")
    if not isinstance(data, list):
        logger.warning("Payload missing 'data' list; got: %s", type(data))
        return []

    products: List[ProductStockInfo] = []
    for obj in data:
        if not isinstance(obj, dict):
            continue
        product_id = str(obj.get("_id", "unknown"))
        name = str(obj.get("name", "Unnamed Product"))

        # Normalize available flag
        available = obj.get("available")
        try:
            available_flag = str(available) in {"1", "true", "True", "yes", "1.0"} or available is True or available == 1
        except Exception:  # pragma: no cover - defensive
            available_flag = False

        # inventory quantity
        inv_raw = obj.get("inventory_quantity")
        inv_qty: int | None
        try:
            inv_qty = int(inv_raw) if inv_raw is not None else None
        except (ValueError, TypeError):
            inv_qty = None

        in_stock = bool(inv_qty and inv_qty > 0 and available_flag)

        products.append(
            ProductStockInfo(
                product_id=product_id,
                name=name,
                in_stock=in_stock,
                inventory_quantity=inv_qty,
                raw=obj,
            )
        )
    return products


def detect_in_stock_transitions(products: List[ProductStockInfo], state: StockState) -> List[ProductStockInfo]:
    """Return list of products that newly became in stock (False -> True or first sighting in-stock)."""
    newly_available: List[ProductStockInfo] = []
    for p in products:
        changed, prev = state.status_changed(p)
        if changed and p.in_stock and (prev is False or prev is None):
            newly_available.append(p)
    return newly_available


__all__ = [
    "ProductStockInfo",
    "StockState",
    "parse_products",
    "detect_in_stock_transitions",
]
