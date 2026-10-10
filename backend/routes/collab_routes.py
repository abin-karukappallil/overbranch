"""
routes/collab_routes.py — Realtime collaboration endpoints
==========================================================
    POST /api/collab/ticket            issue a one-time websocket ticket
    GET  /api/collab/config            client bootstrap (enabled, intervals)
    GET  /api/collab/rooms/{id}        room introspection for members
    WS   /ws/collab/{project_id}       the y-websocket protocol endpoint

Authorization is resolved **here**, server-side, from `projects.owner_id` and
`project_members` — never from anything the client claims. It is re-resolved
every `COLLAB_REAUTH_INTERVAL` seconds for the lifetime of the socket, so
removing a collaborator ends their live session instead of their next reload.
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from auth import get_current_user_or_guest, validate_better_auth_session
from collab.access import can_edit, resolve_project_role
from collab.config import config
from collab.events import log_error, log_event
from collab.manager import room_manager
from collab.presence import presence_registry, should_open_socket
from collab.room import (
    CLOSE_CREDENTIALS_REQUIRED,
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    CLOSE_PROTOCOL,
    CLOSE_ROOM_FULL,
    CLOSE_UNAUTHORIZED,
    Connection,
)
from collab.tickets import issue_ticket, verify_ticket
from database import get_session_factory
from rate_limiter import RateLimiter

logger = logging.getLogger("routes.collab")

router = APIRouter()


class TicketRequest(BaseModel):
    project_id: str = Field(..., min_length=1)


class PresenceRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    leaving: bool = False


@router.get("/api/collab/config")
def collab_config(request: Request) -> Dict[str, Any]:
    """Unauthenticated bootstrap: capability flags only, no project data."""
    return {
        "enabled": config.enabled,
        "ws_path": "/ws/collab",
        "ticket_path": "/api/collab/ticket",
        "ticket_ttl": config.ticket_ttl,
        "reauth_interval": config.reauth_interval,
        "persist_debounce": config.persist_debounce,
        "text_extensions": list(config.collaborative_files),
        "max_connections_per_room": config.max_connections_per_room,
    }


@router.post(
    "/api/collab/ticket",
    dependencies=[Depends(RateLimiter(times=120, seconds=60, key_prefix="rl_collab_ticket"))],
)
def create_collab_ticket(
    req: TicketRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    """
    Issues a single-use, 60s ticket for `/ws/collab/<project_id>`.

    Guests are refused: guest projects are single-session by construction, and
    they keep the existing REST autosave path. Collaboration is for accounts.
    """
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Collaboration is disabled.")

    if auth_info.get("is_guest"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Realtime collaboration requires a signed-in account.",
        )

    user_id = auth_info.get("user_id")
    role = resolve_project_role(req.project_id, user_id)
    if role is None:
        log_event(
            "COLLAB_AUTH_FAILURE",
            project_id=req.project_id,
            user_id=user_id,
            stage="ticket",
            reason="no_project_access",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project.",
        )

    ticket, ttl = issue_ticket(user_id, req.project_id)
    return {
        "ticket": ticket,
        "expires_in": ttl,
        "role": role,
        "can_edit": can_edit(role),
        "project_id": req.project_id,
    }


@router.post(
    "/api/collab/presence",
    dependencies=[Depends(RateLimiter(times=240, seconds=60, key_prefix="rl_collab_presence"))],
)
def collab_presence(
    req: PresenceRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    """
    Heartbeat: "I have this project open." Answers whether a realtime room is
    worth holding right now.

    This exists so that finding out whether anyone else is here does not
    itself require a websocket. A room costs a connection, a concurrency slot,
    an authoritative CRDT document and a persistence timer for as long as the
    tab is open; the common case is one person editing alone, who needs none
    of it. The caller only opens a socket when `connect` is true.

    It is a hint, never an authorization: `resolve_project_role` still gates
    the socket on connect and every re-auth tick.
    """
    if not config.enabled:
        return {"enabled": False, "connect": False, "viewers": 0, "poll_interval": 0}
    if auth_info.get("is_guest"):
        return {"enabled": False, "connect": False, "viewers": 0, "poll_interval": 0,
                "reason": "guest"}

    user_id = auth_info.get("user_id")
    role = resolve_project_role(req.project_id, user_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You do not have access to this project.")
    if req.leaving:
        presence_registry.leave(req.project_id, user_id)
        return {"enabled": True, "connect": False, "viewers": 0,
                "poll_interval": 0, "reason": "left", "role": role}

    connect, detail = should_open_socket(req.project_id, user_id)
    return {"enabled": True, "connect": connect, "role": role,
            "can_edit": can_edit(role), **detail}


@router.get("/api/collab/rooms/{project_id}")
def describe_room(
    project_id: str,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    """Who is live in a project right now. Members only."""
    user_id = auth_info.get("user_id")
    if auth_info.get("is_guest") or resolve_project_role(project_id, user_id) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    room = room_manager.get(project_id)
    if room is None:
        return {"project_id": project_id, "active": False, "peers": [], "files": []}
    return {"active": True, **room.describe()}


# ============================================================================
# WebSocket endpoint
# ============================================================================

def _origin_allowed(websocket: WebSocket) -> bool:
    """
    Guards against cross-site websocket hijacking.

    Browsers do not apply CORS to WebSocket: `new WebSocket(...)` from any page
    the user has open will carry their Better-Auth cookie. Without this check,
    any site could open a room for a project the user can read. Only browsers
    send `Origin`, so a request without one is not a browser and is left to the
    credential checks.
    """
    if not config.require_origin:
        return True
    origin = (websocket.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        return True
    return origin in config.allowed_origins


async def _authenticate_socket(
    websocket: WebSocket, project_id: str
) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Resolves (user_id, display_name, close_code).

    Two accepted proofs, in order:
      1. `?ticket=` — a one-time HMAC ticket from POST /api/collab/ticket. The
         only option when the browser will not attach cookies to the upgrade.
      2. The Better-Auth session cookie, validated against the shared `session`
         table exactly like every REST route does.

    A WebSocket cannot carry an Authorization header from a browser, which is
    why the session token itself is never accepted in the query string.
    """
    ticket = websocket.query_params.get("ticket")
    if ticket:
        verified = verify_ticket(ticket, project_id)
        if verified is None:
            return None, None, CLOSE_UNAUTHORIZED
        if verified.get("is_guest"):
            return None, None, CLOSE_FORBIDDEN
        return str(verified["user_id"]), None, None

    token: Optional[str] = None
    for name in (
        "__Secure-better-auth.session_token",
        "better-auth.session_token",
        "session_token",
    ):
        raw = websocket.cookies.get(name)
        if raw and raw.strip():
            token = urllib.parse.unquote(raw.strip()).split(".")[0].strip()
            break

    if not token:
        # No ticket and no cookie: the browser simply did not volunteer a
        # credential, which is the normal first attempt on a cross-site
        # deployment. Tell the client to authenticate and come back, rather
        # than that it was refused.
        return None, None, CLOSE_CREDENTIALS_REQUIRED

    try:
        factory = get_session_factory()
        async with factory() as session:
            user, sess = await validate_better_auth_session(token, session)
    except Exception as e:
        log_error("COLLAB_AUTH_FAILURE", e, project_id=project_id, stage="cookie_session")
        return None, None, CLOSE_UNAUTHORIZED

    if not user or not sess:
        return None, None, CLOSE_UNAUTHORIZED
    return user.id, getattr(user, "name", None), None


@router.websocket("/ws/collab/{project_id}")
async def collab_socket(websocket: WebSocket, project_id: str) -> None:
    # The handshake is accepted *before* authorization, then closed with a
    # specific code if the caller has no business here. Closing an ASGI
    # websocket before `accept()` rejects the upgrade itself, and a browser
    # reports that as close code 1006 with no detail — so the client cannot
    # tell "forbidden, stop asking" from "network blip, retry", and y-websocket
    # reconnects forever against a project the user cannot open. Nothing is
    # ever sent on the socket before the checks below pass, and a rejected
    # socket is closed within the same round trip.
    await websocket.accept()

    async def reject(code: int, close_text: str, **fields: Any) -> None:
        log_event("COLLAB_AUTH_FAILURE", project_id=project_id, close_code=code, **fields)
        try:
            await websocket.close(code=code, reason=close_text)
        except Exception:
            pass

    if not config.enabled:
        await reject(CLOSE_FORBIDDEN, "Collaboration disabled", stage="disabled")
        return

    if not _origin_allowed(websocket):
        await reject(
            CLOSE_FORBIDDEN,
            "Origin not allowed",
            stage="origin",
            reason="disallowed_origin",
            origin=websocket.headers.get("origin"),
        )
        return

    user_id, display_name, close_code = await _authenticate_socket(websocket, project_id)
    if close_code is not None or not user_id:
        code = close_code or CLOSE_UNAUTHORIZED
        await reject(code, "Authentication required" if code == CLOSE_CREDENTIALS_REQUIRED else "Unauthorized",
                     stage="handshake",
                     reason="no_credential" if code == CLOSE_CREDENTIALS_REQUIRED else "invalid_credential")
        return

    role = await asyncio.to_thread(resolve_project_role, project_id, user_id)
    if role is None:
        # Covers both "not a member" and "project was deleted".
        await reject(
            CLOSE_FORBIDDEN,
            "Forbidden",
            user_id=user_id,
            stage="authorize",
            reason="no_project_access",
        )
        return

    room = await room_manager.get_or_create(project_id)
    if len(room.connections) >= config.max_connections_per_room:
        log_event("COLLAB_ERROR", project_id=project_id, user_id=user_id, reason="room_full")
        try:
            await websocket.close(code=CLOSE_ROOM_FULL, reason="Room is full")
        except Exception:
            pass
        return

    conn = Connection(websocket, user_id, display_name or user_id, role)
    initial_file = websocket.query_params.get("file") or None

    log_event(
        "COLLAB_CONNECT",
        project_id=project_id,
        user_id=user_id,
        role=role,
        conn_id=conn.id,
        auth="ticket" if websocket.query_params.get("ticket") else "cookie",
    )

    reauth_task: Optional[asyncio.Task] = None
    disconnect_reason = "client_closed"

    try:
        await room.add_connection(conn, initial_file=initial_file)
        reauth_task = asyncio.create_task(_reauth_loop(conn, room, project_id, user_id))

        while True:
            try:
                message = await websocket.receive_bytes()
            except KeyError:
                # A text frame on a binary protocol: ignore rather than drop the
                # connection (some proxies inject keepalive text frames).
                continue
            await room.handle_message(conn, message)
            if conn.close_code is not None:
                disconnect_reason = "protocol_violation"
                await websocket.close(code=conn.close_code, reason="Protocol error")
                break
    except WebSocketDisconnect:
        disconnect_reason = "client_disconnect"
    except asyncio.CancelledError:
        disconnect_reason = "server_shutdown"
        raise
    except Exception as e:
        disconnect_reason = "error"
        log_error("COLLAB_ERROR", e, project_id=project_id, user_id=user_id, conn_id=conn.id)
    finally:
        if reauth_task and not reauth_task.done():
            reauth_task.cancel()
            try:
                await reauth_task
            except (asyncio.CancelledError, Exception):
                pass
        await room.remove_connection(conn)
        log_event(
            "COLLAB_DISCONNECT",
            project_id=project_id,
            user_id=user_id,
            conn_id=conn.id,
            reason=disconnect_reason,
        )


async def _reauth_loop(conn: Connection, room, project_id: str, user_id: str) -> None:
    """
    Re-verifies project access while the socket is open.

    Three outcomes:
      * access revoked / project deleted -> close 4403, client stops retrying
      * role downgraded to Viewer        -> writes start being dropped
      * role upgraded                    -> writes start being accepted
    """
    try:
        while True:
            await asyncio.sleep(config.reauth_interval)
            role = await asyncio.to_thread(resolve_project_role, project_id, user_id)
            if role is None:
                log_event(
                    "COLLAB_AUTH_FAILURE",
                    project_id=project_id,
                    user_id=user_id,
                    conn_id=conn.id,
                    stage="reauth",
                    reason="access_revoked",
                )
                try:
                    await conn.ws.close(code=CLOSE_FORBIDDEN, reason="Access revoked")
                except Exception:
                    pass
                return
            if role != conn.role:
                log_event(
                    "COLLAB_JOIN",
                    project_id=project_id,
                    user_id=user_id,
                    conn_id=conn.id,
                    reason="role_changed",
                    role=role,
                    previous_role=conn.role,
                )
                conn.role = role
    except asyncio.CancelledError:
        raise
    except Exception as e:  # pragma: no cover - defensive
        log_error("COLLAB_ERROR", e, project_id=project_id, user_id=user_id, stage="reauth")
