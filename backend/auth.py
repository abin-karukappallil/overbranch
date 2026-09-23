"""
backend/auth.py — Authentication and Authorization Resolver for OverBranch Backend
=================================================================================
Validates Better Auth session tokens against the shared PostgreSQL database (via SQLAlchemy)
and verifies guest HMAC tokens. Protects endpoints against unauthorized access, DDoS,
scraping, and enforces project-level RBAC.

Cross-Stack Better Auth Verification Flow:
------------------------------------------
1. Next.js 15 (Better Auth) authenticates the client and sets a cookie:
   `better-auth.session_token` or `__Secure-better-auth.session_token`.
2. Better Auth creates a record in the shared PostgreSQL `session` table:
   `session (id, token, user_id, expires_at, ...)`.
3. In browser requests to the FastAPI backend (e.g. SSE agent, PDF convert, compile),
   the cookie is included automatically (via credentials: 'include').
4. FastAPI extracts the token, unquotes it, strips any signature suffix (format: `token.sig`),
   and queries PostgreSQL using async SQLAlchemy:
   `SELECT session JOIN user WHERE session.token = :raw_token AND session.expires_at > NOW()`.
5. If valid and unexpired, the `User` ORM model is injected into the route handler via `Depends(get_current_user)`.
   If missing, invalid, or expired, an HTTP 401 Unauthorized exception is raised immediately.
"""

from __future__ import annotations

import os
import logging
import urllib.parse
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from fastapi import Request, HTTPException, status, Depends, Security
from fastapi.security import APIKeyCookie, HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client

from database import get_db, get_session_factory
from models import User, Session

logger = logging.getLogger("auth")

# ============================================================================
# OpenAPI Security Schemes (for Swagger UI /docs interactive authorization)
# ============================================================================

better_auth_cookie_scheme = APIKeyCookie(
    name="better-auth.session_token",
    description="Better Auth session cookie set by Next.js (format: <token>.<signature>)",
    auto_error=False,
)
bearer_auth_scheme = HTTPBearer(
    description="Bearer token or Better Auth session token (e.g. Bearer <token>)",
    auto_error=False,
)
guest_token_header_scheme = APIKeyHeader(
    name="x-guest-token",
    description="HMAC guest identity token for guest sessions",
    auto_error=False,
)


# ============================================================================
# Token Extraction Helpers
# ============================================================================

def extract_session_token(request: Request) -> Optional[str]:
    """
    Extracts the Better Auth session token from cookies, Authorization header, or custom headers.
    Handles URL-decoding and Better Auth signature stripping.
    """
    token_str: Optional[str] = None

    # 1. Check cookies (standard Better Auth cookie names)
    cookie_names = [
        "__Secure-better-auth.session_token",
        "better-auth.session_token",
        "session_token",
    ]
    for c_name in cookie_names:
        cookie_val = request.cookies.get(c_name)
        if cookie_val and cookie_val.strip():
            token_str = urllib.parse.unquote(cookie_val.strip())
            break

    # 2. Check Authorization Bearer header if not found in cookies
    if not token_str:
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token_str = auth_header[7:].strip()

    # 3. Check custom auth headers
    if not token_str:
        custom_token = (
            request.headers.get("x-auth-token")
            or request.headers.get("x-session-token")
            or request.headers.get("X-Auth-Token")
            or request.headers.get("X-Session-Token")
        )
        if custom_token:
            token_str = custom_token.strip()

    if not token_str:
        return None

    # Clean raw token: Better Auth cookie values often have the format: `<token>.<signature>`
    if "." in token_str:
        return token_str.split(".")[0].strip()

    return token_str.strip()


def extract_bearer_token(request: Request) -> Optional[str]:
    """Backward-compatible alias for extract_session_token."""
    return extract_session_token(request)


def extract_guest_token(request: Request) -> Optional[str]:
    """
    Extracts guest token from custom header or cookie.
    """
    from services.guest_identity import GUEST_TOKEN_COOKIE_NAME

    header_token = request.headers.get("x-guest-token") or request.headers.get("X-Guest-Token")
    if header_token:
        return header_token.strip()

    cookie_token = request.cookies.get(GUEST_TOKEN_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip()

    return None


# ============================================================================
# Better Auth SQLAlchemy Validation Helpers
# ============================================================================

async def validate_better_auth_session(
    token: str,
    db: AsyncSession,
) -> Tuple[Optional[User], Optional[Session]]:
    """
    Queries PostgreSQL for the session token, verifies expiration,
    and returns (User, Session) if valid.
    """
    raw_token = token.split(".")[0].strip()

    # Query session joining user
    stmt = (
        select(Session)
        .where(Session.token.in_([raw_token, token]))
        .limit(1)
    )
    result = await db.execute(stmt)
    sess: Optional[Session] = result.scalars().first()

    if not sess:
        logger.debug(f"Session token not found in database: token_prefix={raw_token[:8]}...")
        return None, None

    # Validate expiration
    if sess.is_expired():
        logger.warning(
            f"Expired Better-Auth session for user {sess.user_id} (expired at {sess.expires_at})"
        )
        return None, None

    if not sess.user:
        logger.warning(f"Session {sess.id} exists but associated User ({sess.user_id}) was not found.")
        return None, None

    return sess.user, sess


# ============================================================================
# FastAPI Dependencies
# ============================================================================

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cookie_token: Optional[str] = Security(better_auth_cookie_scheme),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth_scheme),
) -> User:
    """
    FastAPI dependency requiring an authenticated Better Auth user session.
    Extracts the session token from cookies or headers, validates it against
    the shared PostgreSQL database via SQLAlchemy, and returns the User object.

    Swagger UI Integration:
    - Displays the 'Authorize' button in Swagger UI (/docs)
    - Displays the padlock icon on protected endpoints
    - Supports both Better Auth session cookie and Bearer token

    Raises HTTP 401 Unauthorized if:
    - No session token or cookie is provided.
    - The session token does not exist in the database.
    - The session has expired.
    """
    # 1. Check Swagger UI security injected parameters, then fallback to request
    token: Optional[str] = None
    if isinstance(bearer_creds, HTTPAuthorizationCredentials) and bearer_creds.credentials:
        token = bearer_creds.credentials.strip()
        if "." in token:
            token = token.split(".")[0].strip()
    elif isinstance(cookie_token, str) and cookie_token.strip():
        token = urllib.parse.unquote(cookie_token.strip())
        if "." in token:
            token = token.split(".")[0].strip()
    else:
        token = extract_session_token(request)

    if not token:
        logger.info(f"Unauthenticated request to protected endpoint: {request.url.path} (missing session token/cookie)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Better Auth session token or cookie.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, sess = await validate_better_auth_session(token, db)
    if not user or not sess:
        logger.warning(f"Rejected invalid or expired session token for {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attach to request state for downstream middlewares / logging / rate limiters
    request.state.user = user
    request.state.user_id = user.id
    request.state.session_id = sess.id

    return user


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cookie_token: Optional[str] = Security(better_auth_cookie_scheme),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth_scheme),
) -> Optional[User]:
    """
    FastAPI dependency that returns the authenticated User if a valid session exists,
    or None if no session credentials were provided.
    """
    token: Optional[str] = None
    if isinstance(bearer_creds, HTTPAuthorizationCredentials) and bearer_creds.credentials:
        token = bearer_creds.credentials.strip()
        if "." in token:
            token = token.split(".")[0].strip()
    elif isinstance(cookie_token, str) and cookie_token.strip():
        token = urllib.parse.unquote(cookie_token.strip())
        if "." in token:
            token = token.split(".")[0].strip()
    else:
        token = extract_session_token(request)

    if not token:
        return None

    user, sess = await validate_better_auth_session(token, db)
    if user and sess:
        request.state.user = user
        request.state.user_id = user.id
        request.state.session_id = sess.id
        return user

    return None


async def get_current_user_or_guest(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cookie_token: Optional[str] = Security(better_auth_cookie_scheme),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth_scheme),
    guest_header: Optional[str] = Security(guest_token_header_scheme),
) -> Dict[str, Any]:
    """
    FastAPI dependency that permits both authenticated Better Auth users and verified guest sessions,
    while strictly rejecting unauthenticated scraping and anonymous requests with HTTP 401.
    """
    # 1. Try Better Auth session
    token: Optional[str] = None
    if isinstance(bearer_creds, HTTPAuthorizationCredentials) and bearer_creds.credentials:
        token = bearer_creds.credentials.strip()
        if "." in token:
            token = token.split(".")[0].strip()
    elif isinstance(cookie_token, str) and cookie_token.strip():
        token = urllib.parse.unquote(cookie_token.strip())
        if "." in token:
            token = token.split(".")[0].strip()
    else:
        token = extract_session_token(request)

    if token:
        user, sess = await validate_better_auth_session(token, db)
        if user and sess:
            request.state.user = user
            request.state.user_id = user.id
            request.state.session_id = sess.id
            return {
                "user_id": user.id,
                "session_id": sess.id,
                "is_guest": False,
                "authenticated": True,
                "user": user,
            }

    # 2. Try Guest HMAC token
    from services.guest_identity import verify_guest_token
    guest_tok = guest_header if isinstance(guest_header, str) and guest_header.strip() else None
    if not guest_tok:
        guest_tok = extract_guest_token(request)
    if guest_tok:
        verified = verify_guest_token(guest_tok)
        if verified:
            session_id, _ = verified
            guest_user_id = f"guest_{session_id}"
            request.state.user_id = guest_user_id
            request.state.session_id = session_id
            return {
                "user_id": guest_user_id,
                "session_id": session_id,
                "is_guest": True,
                "authenticated": False,
                "user": None,
            }
        else:
            logger.warning("Invalid or expired guest HMAC token provided")

    # 3. Development / Explicit user header support (strictly disabled in production)
    is_prod = os.getenv("NODE_ENV") == "production" or os.getenv("ENVIRONMENT") == "production"
    if not is_prod:
        explicit_user = request.headers.get("x-user-id") or request.headers.get("X-User-Id")
        if explicit_user:
            return {
                "user_id": explicit_user,
                "session_id": None,
                "is_guest": explicit_user.startswith("guest"),
                "authenticated": not explicit_user.startswith("guest"),
                "user": None,
            }

    # Unauthenticated -> HTTP 401
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide a valid Better Auth session cookie or guest token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ============================================================================
# Backward-Compatible Identity Resolver
# ============================================================================

async def resolve_auth_async(
    request: Request,
    db: Optional[AsyncSession] = None,
) -> Optional[Dict[str, Any]]:
    """
    Asynchronously resolves caller identity using SQLAlchemy for Better Auth sessions
    and HMAC verification for guest tokens.
    """
    # 1. If user already resolved and attached to request.state, return immediately
    if hasattr(request.state, "user") and request.state.user:
        return {
            "user_id": request.state.user.id,
            "session_id": getattr(request.state, "session_id", None),
            "is_guest": False,
            "authenticated": True,
            "user": request.state.user,
        }
    if hasattr(request.state, "user_id") and request.state.user_id:
        is_guest = getattr(request.state, "user_id", "").startswith("guest")
        return {
            "user_id": request.state.user_id,
            "session_id": getattr(request.state, "session_id", None),
            "is_guest": is_guest,
            "authenticated": not is_guest,
            "user": getattr(request.state, "user", None),
        }

    # 2. Check Better Auth session token
    token = extract_session_token(request)
    if token:
        try:
            if db is not None:
                user, sess = await validate_better_auth_session(token, db)
            else:
                factory = get_session_factory()
                async with factory() as session:
                    user, sess = await validate_better_auth_session(token, session)

            if user and sess:
                request.state.user = user
                request.state.user_id = user.id
                request.state.session_id = sess.id
                return {
                    "user_id": user.id,
                    "session_id": sess.id,
                    "is_guest": False,
                    "authenticated": True,
                    "user": user,
                }
        except Exception as e:
            logger.warning(f"Error validating session token against PostgreSQL via SQLAlchemy: {e}")

    # 3. Check for Guest HMAC token
    guest_tok = extract_guest_token(request)
    if guest_tok:
        from services.guest_identity import verify_guest_token
        verified = verify_guest_token(guest_tok)
        if verified:
            session_id, _ = verified
            guest_id = f"guest_{session_id}"
            request.state.user_id = guest_id
            return {
                "user_id": guest_id,
                "session_id": session_id,
                "is_guest": True,
                "authenticated": False,
                "user": None,
            }

    # 4. Development / Explicit user header support (only non-production)
    is_prod = os.getenv("NODE_ENV") == "production" or os.getenv("ENVIRONMENT") == "production"
    if not is_prod:
        explicit_user = request.headers.get("x-user-id") or request.headers.get("X-User-Id")
        if explicit_user:
            return {
                "user_id": explicit_user,
                "session_id": None,
                "is_guest": explicit_user.startswith("guest"),
                "authenticated": not explicit_user.startswith("guest"),
                "user": None,
            }

    return None


def resolve_auth(
    request: Request,
    supabase: Optional[Client] = None,
) -> Optional[Dict[str, Any]]:
    """
    Synchronous fallback wrapper for resolve_auth.
    Checks request.state first; if not present, falls back to Supabase client or DB check.
    """
    if hasattr(request.state, "user") and request.state.user:
        return {
            "user_id": request.state.user.id,
            "session_id": getattr(request.state, "session_id", None),
            "is_guest": False,
            "authenticated": True,
            "user": request.state.user,
        }
    if hasattr(request.state, "user_id") and request.state.user_id:
        is_guest = getattr(request.state, "user_id", "").startswith("guest")
        return {
            "user_id": request.state.user_id,
            "session_id": getattr(request.state, "session_id", None),
            "is_guest": is_guest,
            "authenticated": not is_guest,
            "user": getattr(request.state, "user", None),
        }

    # If Better Auth token is present, validate against database or Supabase
    token = extract_session_token(request)
    if token:
        raw_token = token.split(".")[0]
        try:
            from project_storage import get_supabase_client
            sb = supabase or get_supabase_client()
            res = (
                sb.table("session")
                .select("id, user_id, expires_at")
                .eq("token", raw_token)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                sess = rows[0]
                expires_at_str = sess.get("expires_at")
                if expires_at_str:
                    clean_str = str(expires_at_str).replace("Z", "+00:00")
                    expires_at = datetime.fromisoformat(clean_str)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) <= expires_at:
                        return {
                            "user_id": sess["user_id"],
                            "session_id": sess["id"],
                            "is_guest": False,
                            "authenticated": True,
                        }
                    else:
                        logger.warning(f"Expired Better-Auth session token for user {sess.get('user_id')}")
                else:
                    return {
                        "user_id": sess["user_id"],
                        "session_id": sess["id"],
                        "is_guest": False,
                        "authenticated": True,
                    }
        except Exception as e:
            logger.warning(f"Error validating session token in fallback sync resolver: {e}")

    # Guest check
    guest_tok = extract_guest_token(request)
    if guest_tok:
        from services.guest_identity import verify_guest_token
        verified = verify_guest_token(guest_tok)
        if verified:
            session_id, _ = verified
            return {
                "user_id": f"guest_{session_id}",
                "session_id": session_id,
                "is_guest": True,
                "authenticated": False,
            }

    # Dev explicit user check
    is_prod = os.getenv("NODE_ENV") == "production" or os.getenv("ENVIRONMENT") == "production"
    if not is_prod:
        explicit_user = request.headers.get("x-user-id") or request.headers.get("X-User-Id")
        if explicit_user:
            return {
                "user_id": explicit_user,
                "session_id": None,
                "is_guest": explicit_user.startswith("guest"),
                "authenticated": not explicit_user.startswith("guest"),
            }

    return None


# ============================================================================
# Project Ownership & Membership Verification
# ============================================================================

def verify_project_ownership_or_member(
    supabase: Client,
    project_id: str,
    user_id: str,
    is_guest: bool = False,
):
    """
    Verifies that the project belongs to the user or the user is an active collaborator.
    Raises HTTP 403 Forbidden if access is denied.
    """
    if not project_id or not user_id:
        return

    # Scratchpad and default projects are always accessible to the active caller
    if project_id in ("proj-default", "default", "scratchpad") or project_id.startswith("proj-default"):
        return

    # Guest user matching
    if is_guest or user_id.startswith("guest"):
        try:
            guest_sess = user_id.replace("guest_", "").replace("guest-", "")
            gp = (
                supabase.table("guest_projects")
                .select("id")
                .eq("project_id", project_id)
                .eq("guest_session_id", guest_sess)
                .limit(1)
                .execute()
            )
            if gp.data and len(gp.data) > 0:
                return
        except Exception as ge:
            logger.warning(f"Guest project verification lookup error: {ge}")

    # Standard project check
    try:
        proj_res = supabase.table("projects").select("id, owner_id").eq("id", project_id).limit(1).execute()
        rows = proj_res.data or []
        if rows:
            owner_id = rows[0].get("owner_id")
            if owner_id == user_id or owner_id == "default-user" or owner_id.startswith("guest"):
                return
            # Check project_members
            mem_res = (
                supabase.table("project_members")
                .select("id, role")
                .eq("project_id", project_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if mem_res.data and len(mem_res.data) > 0:
                return
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have access to this project."
            )
    except HTTPException:
        raise
    except Exception as err:
        logger.warning(f"Project access check database error: {err}")
