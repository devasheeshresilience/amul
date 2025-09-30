"""Product data fetching utilities.

Enhancement features:
- Supports live HTTP fetch if API_ENDPOINT env var is set.
- Falls back to local file (PAYLOAD_FILE) or SAMPLE_PAYLOAD.
- Implements timeout and basic retry with backoff.

Environment variables:
- API_ENDPOINT: Full URL to fetch JSON.
- FETCH_TIMEOUT: Seconds (default 15).
- FETCH_RETRIES: Retry attempts (default 2 additional tries).

Future: Add auth headers / cookies if required.
"""
from __future__ import annotations

import json
import os
import time
import random
import logging
from pathlib import Path
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

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


def _load_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # pragma: no cover
            logger.error("Failed to read payload file %s: %s", path, e)
    return SAMPLE_PAYLOAD


def fetch_payload() -> Dict[str, Any]:
    """Fetch product payload using precedence:
    1. API_ENDPOINT (live HTTP)
    2. PAYLOAD_FILE (local JSON file)
    3. SAMPLE_PAYLOAD fallback
    """
    endpoint = os.getenv("API_ENDPOINT")
    if endpoint:
        timeout = float(os.getenv("FETCH_TIMEOUT", "15"))
        retries = int(os.getenv("FETCH_RETRIES", "2"))
        backoff_base = 0.75
        for attempt in range(retries + 1):
            try:
                resp = requests.get(endpoint, timeout=timeout, headers={"Accept": "application/json"})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # pragma: no cover - network variability
                logger.warning("Fetch attempt %d failed: %s", attempt + 1, e)
                if attempt < retries:
                    sleep_for = backoff_base * (2 ** attempt) + random.random() * 0.3
                    time.sleep(sleep_for)
                else:
                    logger.error("All fetch attempts failed; falling back")
    file_path = os.getenv("PAYLOAD_FILE")
    if file_path:
        return _load_file(file_path)
    return SAMPLE_PAYLOAD

__all__ = ["fetch_payload"]
