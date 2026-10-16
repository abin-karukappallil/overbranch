"""
web2api_keys.py — Gemini Web2API credential loader used by GeminiProvider.

Discovers GEMINI_WEB2API_BASE_URL and up to five rotating keys
(GEMINI_WEB2API_API_KEY_1..5, or a single / comma-separated GEMINI_WEB2API_API_KEY(S)).

``namespace`` names a SECOND Web2API deployment, so the same loader serves the
fallback endpoint: ``namespace="GEMINI2"`` reads GEMINI2_WEB2API_BASE_URL and
GEMINI2_WEB2API_API_KEY_1..5. The default, "GEMINI", is the primary endpoint and
reads exactly the variables it always did.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

MAX_KEYS = 5


@dataclass(frozen=True)
class Web2ApiKey:
    name: str
    key: str


def get_web2api_base_url(namespace: str = "GEMINI") -> str:
    ns = (namespace or "GEMINI").rstrip("_")
    return (os.getenv(f"{ns}_WEB2API_BASE_URL") or "").strip().rstrip("/")


def load_web2api_keys(namespace: str = "GEMINI") -> List[Web2ApiKey]:
    """Numbered slots 1..MAX_KEYS first, then single or comma-separated keys; duplicates ignored."""
    ns = (namespace or "GEMINI").rstrip("_")
    keys: List[Web2ApiKey] = []
    seen: set = set()

    for i in range(1, MAX_KEYS + 1):
        for var in (
            f"{ns}_WEB2API_API_KEY_{i}",
            f"{ns}_WEB2API_KEY_{i}",
            f"{ns}_API_KEY_{i}",
            f"{ns}_KEY_{i}",
            f"{ns}_{i}",
        ):
            val = (os.getenv(var) or "").strip()
            if val and val not in seen:
                keys.append(Web2ApiKey(name=f"Gemini Key {i}", key=val))
                seen.add(val)
                break

    general = (
        os.getenv(f"{ns}_WEB2API_API_KEYS", "")
        or os.getenv(f"{ns}_WEB2API_API_KEY", "")
        or os.getenv(f"{ns}_API_KEYS", "")
        or os.getenv(f"{ns}_API_KEY", "")
    )
    for piece in general.split(","):
        if len(keys) >= MAX_KEYS:
            break
        k = piece.strip()
        if k and k not in seen:
            keys.append(Web2ApiKey(name=f"Gemini Key {len(keys) + 1}", key=k))
            seen.add(k)

    return keys
