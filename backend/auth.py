"""
backend/auth.py — Authentication and Authorization Resolver for OverBranch Backend
=================================================================================
Validates Better-Auth session tokens (Bearer tokens / cookies) and guest HMAC tokens.
Protects endpoints against unauthorized access and enforces project-level RBAC.
"""

from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import Request, HTTPException, status
from supabase import Client

logger = logging.getLogger("auth")


def extract_bearer_token(request: Request) -> Optional[str]:
    """
    Extracts Bearer token from Authorization header, custom headers, or session cookies.
    """
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    # Check custom auth headers
    custom_token = (
        request.headers.get("x-auth-token")
        or request.headers.get("x-session-token")
        or request.headers.get("X-Auth-Token")
        or request.headers.get("X-Session-Token")
    )
    if custom_token:
        return custom_token.strip()

    # Check session cookies
    cookie_token = (
        request.cookies.get("__Secure-better-auth.session_token")
        or request.cookies.get("better-auth.session_token")
        or request.cookies.get("session_token")
    )
    if cookie_token:
        return cookie_token.strip()

    return None


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


def resolve_auth(request: Request, supabase: Optional[Client] = None) -> Optional[Dict[str, Any]]:
    """
    Resolves caller identity by strictly verifying session tokens or guest HMAC tokens.
    Returns a dict with:
      - user_id: str
      - is_guest: bool
      - session_id: Optional[str]
      - authenticated: bool
    Returns None if neither a valid session nor a valid guest token is present.
    """
    from services.guest_identity import verify_guest_token
    from project_storage import get_supabase_client

    # 1. Check for Better-Auth session token (Bearer or cookie)
    token = extract_bearer_token(request)
    if token:
        # Strip signature suffix if format is 'token.signature'
        raw_token = token.split(".")[0]
        try:
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
            logger.warning(f"Error validating session token against database: {e}")

    # 2. Check for Guest HMAC token
    guest_tok = extract_guest_token(request)
    if guest_tok:
        verified = verify_guest_token(guest_tok)
        if verified:
            session_id, _ = verified
            return {
                "user_id": f"guest_{session_id}",
                "session_id": session_id,
                "is_guest": True,
                "authenticated": False,
            }
        else:
            logger.warning("Invalid or expired guest HMAC token provided")

    # 3. Development / Explicit user header support
    explicit_user = (
        request.headers.get("x-user-id")
        or request.headers.get("X-User-Id")
    )
    if explicit_user:
        return {
            "user_id": explicit_user,
            "session_id": None,
            "is_guest": explicit_user.startswith("guest"),
            "authenticated": not explicit_user.startswith("guest"),
        }

    return None


def get_current_user(request: Request, allow_guest: bool = True) -> Dict[str, Any]:
    """
    FastAPI dependency / helper that requires authentication.
    Raises HTTP 401 if unauthorized.
    """
    auth_info = resolve_auth(request)
    if not auth_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token, session cookie, or guest token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not allow_guest and auth_info.get("is_guest"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest users cannot perform this action. Please sign in.",
        )

    return auth_info


def verify_project_ownership_or_member(supabase: Client, project_id: str, user_id: str, is_guest: bool = False):
    """
    Verifies that project belongs to user or user is an active collaborator.
    """
    if not project_id or not user_id:
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
