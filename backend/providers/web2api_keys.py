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
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

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


# ---------------------------------------------------------------------------
# Gateway chain (WEB2API_GATEWAYS)
# ---------------------------------------------------------------------------
#
# The deployment runs several self-hosted Web2API Gemini gateways. Every request
# tries them in the configured order and cycles the whole chain LLM_CHAIN_CYCLES
# times. They share ONE key (WEB2API_API_KEY); nothing else is ever called.
#
#   WEB2API_GATEWAYS="https://g1.overbranch.app/v1,https://g2.overbranch.app/v1,..."
#   WEB2API_API_KEY="..."
#   LLM_CHAIN_CYCLES=12
#
# With WEB2API_GATEWAYS unset the chain is built from the older per-endpoint
# variables (GEMINI_WEB2API_* then GEMINI2_WEB2API_*), so existing .env files work.

DEFAULT_CHAIN_CYCLES = 12


@dataclass(frozen=True)
class GatewaySpec:
    """One chain entry. ``base_url`` None means "read it from ``namespace``'s env vars"."""
    name: str                       # unique chain name, e.g. "G1"
    namespace: str                  # env namespace used for per-gateway key / timeout lookups
    base_url: Optional[str] = None
    shared_key: bool = False        # keys come from WEB2API_API_KEY
    label: str = ""


def _normalize_url(raw: str) -> str:
    url = (raw or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "https://" + url
    return url


def get_gateway_urls() -> List[str]:
    """WEB2API_GATEWAYS as an ordered list of base URLs (commas or newlines, blanks ignored)."""
    raw = os.getenv("WEB2API_GATEWAYS") or ""
    return [u for u in (_normalize_url(p) for p in raw.replace("\n", ",").split(",")) if u]


def get_shared_keys() -> List[Web2ApiKey]:
    """The key shared by every WEB2API_GATEWAYS entry (WEB2API_API_KEY, or a comma-separated WEB2API_API_KEYS)."""
    raw = os.getenv("WEB2API_API_KEYS") or os.getenv("WEB2API_API_KEY") or ""
    keys: List[Web2ApiKey] = []
    seen: set = set()
    for piece in raw.split(","):
        k = piece.strip()
        if k and k not in seen and len(keys) < MAX_KEYS:
            keys.append(Web2ApiKey(name=f"Gateway Key {len(keys) + 1}", key=k))
            seen.add(k)
    return keys


def get_chain_cycles() -> int:
    try:
        return max(1, int(os.getenv("LLM_CHAIN_CYCLES", DEFAULT_CHAIN_CYCLES)))
    except ValueError:
        return DEFAULT_CHAIN_CYCLES


def _host_label(url: str) -> str:
    host = urlparse(url).hostname or url
    label = re.sub(r"[^A-Za-z0-9]+", "_", host.split(".")[0]).strip("_").upper()
    return label or "GATEWAY"


def get_gateway_specs() -> List[GatewaySpec]:
    """The ordered chain: WEB2API_GATEWAYS when set, else the legacy GEMINI / GEMINI2 endpoints."""
    urls = get_gateway_urls()
    if urls:
        specs: List[GatewaySpec] = []
        taken: set = set()
        for i, url in enumerate(urls, 1):
            name = _host_label(url)
            if name in taken:
                name = f"{name}_{i}"
            taken.add(name)
            specs.append(GatewaySpec(name=name, namespace=name, base_url=url, shared_key=True,
                                     label=f"Gateway {name}"))
        return specs
    legacy = []
    if get_web2api_base_url("GEMINI"):
        legacy.append(GatewaySpec(name="GEMINI", namespace="GEMINI", label="Gemini"))
    if get_web2api_base_url("GEMINI2"):
        legacy.append(GatewaySpec(name="GEMINI2", namespace="GEMINI2", label="Gemini (secondary)"))
    return legacy


def gateways_configured() -> bool:
    """True when at least one gateway has a URL and a key."""
    for spec in get_gateway_specs():
        if spec.shared_key:
            if get_shared_keys():
                return True
        elif load_web2api_keys(spec.namespace):
            return True
    return False
