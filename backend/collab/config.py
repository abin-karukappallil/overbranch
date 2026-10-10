"""
backend/collab/config.py — Real-time collaboration settings (non-LLM, env driven)
=================================================================================
Every knob is an environment variable so the collaboration layer can be tuned
per deployment without a code change. Defaults are chosen for the single-node
Docker deployment described in DOCKER_DEPLOYMENT.md.
"""

from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


class CollabConfig:
    """Read on every access so tests (and reloads) can monkeypatch the env."""

    @property
    def enabled(self) -> bool:
        return _bool("COLLAB_ENABLED", True)

    # ── Persistence ───────────────────────────────────────────────────────────
    @property
    def persist_debounce(self) -> float:
        """Seconds of edit silence before a dirty file is written to storage."""
        return _float("COLLAB_PERSIST_DEBOUNCE", 2.0)

    @property
    def persist_max_interval(self) -> float:
        """A continuously edited file is still written at least this often."""
        return _float("COLLAB_PERSIST_MAX_INTERVAL", 15.0)

    @property
    def persist_tick(self) -> float:
        return _float("COLLAB_PERSIST_TICK", 0.5)

    # ── Room lifecycle ────────────────────────────────────────────────────────
    @property
    def room_idle_ttl(self) -> float:
        """Seconds an empty room is kept in memory before it is flushed+dropped."""
        return _float("COLLAB_ROOM_IDLE_TTL", 60.0)

    @property
    def max_connections_per_room(self) -> int:
        return _int("COLLAB_MAX_CONNECTIONS_PER_ROOM", 32)

    @property
    def max_rooms(self) -> int:
        return _int("COLLAB_MAX_ROOMS", 500)

    # ── Authorization ─────────────────────────────────────────────────────────
    @property
    def reauth_interval(self) -> float:
        """How often an open connection's project access is re-verified."""
        return _float("COLLAB_REAUTH_INTERVAL", 30.0)

    @property
    def ticket_ttl(self) -> int:
        """Seconds a websocket ticket stays valid (one-time use)."""
        return _int("COLLAB_TICKET_TTL", 60)

    @property
    def ticket_secret(self) -> str:
        return (
            os.getenv("COLLAB_TICKET_SECRET")
            or os.getenv("BETTER_AUTH_SECRET")
            or "overbranch-collab-ticket-secret-replace-in-production"
        )

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """
        Origins permitted to open a collaboration websocket.

        Browsers do not apply CORS to WebSocket, so a cookie-authenticated
        socket must check `Origin` itself or any site the user visits could
        open one with their session cookie and read a private document
        (cross-site websocket hijacking). Falls back to the same variables the
        HTTP CORS layer uses in main.py.
        """
        raw = (
            os.getenv("COLLAB_ALLOWED_ORIGINS")
            or os.getenv("ALLOWED_ORIGINS")
            or ""
        )
        # .env values in this project are often quoted; python-dotenv strips
        # them, but a value injected straight into the environment may not be.
        def clean(value: str) -> str:
            return value.strip().strip('"').strip("'").rstrip("/")

        origins = [clean(o) for o in raw.split(",") if o.strip()]
        for var in ("NEXT_PUBLIC_APP_URL", "BETTER_AUTH_URL"):
            value = clean(os.getenv(var) or "")
            if value:
                origins.append(value)
        if not origins:
            origins = [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "https://overbranch.abinthomas.dev",
            ]
        return tuple(dict.fromkeys(origins))

    @property
    def require_origin(self) -> bool:
        """
        COLLAB_REQUIRE_ORIGIN=0 turns the Origin check off — for a non-browser
        client (a test harness, a CLI) that sends no Origin at all. A missing
        Origin header is always allowed, since only browsers send one; the
        check exists to stop a *browser* on another site, which cannot omit it.
        """
        return _bool("COLLAB_REQUIRE_ORIGIN", True)

    # ── Safety limits ─────────────────────────────────────────────────────────
    @property
    def max_message_bytes(self) -> int:
        return _int("COLLAB_MAX_MESSAGE_BYTES", 2 * 1024 * 1024)

    @property
    def max_file_bytes(self) -> int:
        return _int("COLLAB_MAX_FILE_BYTES", 4 * 1024 * 1024)

    @property
    def max_files_per_room(self) -> int:
        return _int("COLLAB_MAX_FILES_PER_ROOM", 64)

    @property
    def send_queue_size(self) -> int:
        return _int("COLLAB_SEND_QUEUE_SIZE", 256)

    # ── Observability ─────────────────────────────────────────────────────────
    @property
    def debug(self) -> bool:
        """COLLAB_DEBUG=1 promotes per-message events from DEBUG to INFO."""
        return _bool("COLLAB_DEBUG", False)

    @property
    def collaborative_files(self) -> tuple[str, ...]:
        """
        Extensions whose content is synchronized as text. Binary assets stay on
        the existing upload path — a CRDT of a PNG buys nothing.
        """
        raw = os.getenv("COLLAB_TEXT_EXTENSIONS", ".tex,.bib,.cls,.sty,.txt,.md,.bbl")
        return tuple(e.strip().lower() for e in raw.split(",") if e.strip())


config = CollabConfig()
