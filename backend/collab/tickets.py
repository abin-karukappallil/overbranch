"""
backend/collab/tickets.py — One-time websocket admission tickets
================================================================
A browser cannot set headers on a WebSocket handshake, so a cross-origin
connection has only two ways to prove who it is: the cookie (sent when the
backend is same-site with the app, which is the normal OverBranch deployment:
`overbranch.…dev` → `overapi.…dev`) or a token in the URL.

Putting the Better-Auth *session* token in a URL would leak it into proxy logs,
browser history and `Referer`. So the client first calls the authenticated REST
endpoint `POST /api/collab/ticket`, which issues a short-lived, single-use,
HMAC-signed ticket bound to (user, project). The ticket is worthless after one
use or `COLLAB_TICKET_TTL` seconds, and carries no secret of its own.

The ticket is an *identity* assertion only. Project access is still re-checked
against `project_members` when the socket opens and every
`COLLAB_REAUTH_INTERVAL` seconds while it is open, so a revoked collaborator
loses access even mid-session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from threading import Lock
from typing import Dict, Optional, Tuple

from .config import config


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class TicketStore:
    """
    Tracks which tickets have been redeemed so each one works exactly once.
    In-memory by design: a ticket lives for seconds, and a replay from another
    worker still has to pass the full membership check on connect.
    """

    def __init__(self) -> None:
        self._used: Dict[str, float] = {}
        self._lock = Lock()

    def _purge(self, now: float) -> None:
        cutoff = now - (config.ticket_ttl + 5)
        for nonce in [n for n, ts in self._used.items() if ts < cutoff]:
            self._used.pop(nonce, None)

    def redeem(self, nonce: str) -> bool:
        """True if this nonce had not been used yet."""
        now = time.time()
        with self._lock:
            self._purge(now)
            if nonce in self._used:
                return False
            self._used[nonce] = now
            return True

    def clear(self) -> None:
        with self._lock:
            self._used.clear()


ticket_store = TicketStore()


def issue_ticket(user_id: str, project_id: str, *, is_guest: bool = False) -> Tuple[str, int]:
    """
    Returns `(ticket, expires_in_seconds)`.

    Format: `v1.<user_id_b64>.<project_id_b64>.<guest>.<issued_at>.<nonce>.<sig>`
    """
    issued_at = int(time.time())
    nonce = _b64(os.urandom(12))
    payload = ".".join(
        [
            "v1",
            _b64(user_id.encode()),
            _b64(project_id.encode()),
            "1" if is_guest else "0",
            str(issued_at),
            nonce,
        ]
    )
    sig = hmac.new(config.ticket_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}", config.ticket_ttl


def verify_ticket(ticket: Optional[str], project_id: str) -> Optional[Dict[str, object]]:
    """
    Verifies signature, expiry, project binding and single use.
    Returns `{"user_id": …, "is_guest": bool}` or None.
    """
    if not ticket:
        return None
    parts = ticket.split(".")
    if len(parts) != 7 or parts[0] != "v1":
        return None

    payload = ".".join(parts[:6])
    provided_sig = parts[6]
    expected_sig = hmac.new(
        config.ticket_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    try:
        user_id = base64.urlsafe_b64decode(parts[1] + "==").decode()
        ticket_project = base64.urlsafe_b64decode(parts[2] + "==").decode()
        issued_at = int(parts[4])
    except Exception:
        return None

    if ticket_project != project_id:
        return None

    now = int(time.time())
    # A small negative tolerance covers clock skew between workers.
    if issued_at > now + 5 or now - issued_at > config.ticket_ttl:
        return None

    if not ticket_store.redeem(parts[5]):
        return None

    return {"user_id": user_id, "is_guest": parts[3] == "1"}
