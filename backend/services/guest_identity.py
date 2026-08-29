"""
guest_identity.py — Cryptographic Identity & Device Fingerprinting for Guest Sessions

Provides:
- Composite device fingerprinting: SHA-256(User-Agent + Accept-Language + Sec-CH-UA + Hashed IP)
- HMAC-SHA256 token generation and constant-time verification
- Cookie parsing, session lookup, and recovery against cookie-clearing abuse
- Automatic provisioning of temporary guest user rows to maintain relational foreign key integrity
"""

import os
import time
import hmac
import uuid
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any
from fastapi import Request, Response

from project_storage import get_supabase_client

logger = logging.getLogger("guest_identity")

GUEST_TOKEN_COOKIE_NAME = "ob_guest_token"
SESSION_LIFETIME_SECONDS = 86400  # 24 hours

GUEST_SECRET = os.getenv("GUEST_TOKEN_SECRET", "overbranch-guest-super-secret-key-replace-2026")


def parse_utc_datetime(val: Any) -> datetime:
    """Safely converts string or datetime into UTC offset-aware datetime."""
    if isinstance(val, datetime):
        dt = val
    else:
        clean_str = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_client_ip(request: Request) -> str:
    """Extracts client IP address respecting reverse proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def compute_device_fingerprint(request: Request) -> str:
    """
    Generates a deterministic SHA-256 device fingerprint.
    Components:
    - User-Agent
    - Accept-Language
    - Client Hints: sec-ch-ua, sec-ch-ua-platform, sec-ch-ua-mobile
    - Salted client IP
    """
    ua = request.headers.get("user-agent", "").strip()
    lang = request.headers.get("accept-language", "").strip()
    ch_ua = request.headers.get("sec-ch-ua", "").strip()
    ch_platform = request.headers.get("sec-ch-ua-platform", "").strip()
    ch_mobile = request.headers.get("sec-ch-ua-mobile", "").strip()
    
    ip = get_client_ip(request)
    ip_hash = hashlib.sha256(f"{GUEST_SECRET}:{ip}".encode("utf-8")).hexdigest()[:16]

    raw_composite = f"{ua}|{lang}|{ch_ua}|{ch_platform}|{ch_mobile}|{ip_hash}"
    return hashlib.sha256(raw_composite.encode("utf-8")).hexdigest()


def sign_guest_token(session_id: str, timestamp: Optional[int] = None) -> str:
    """
    Creates an HMAC-SHA256 signed token:
    format: {session_id}.{timestamp}.{signature}
    """
    ts = timestamp or int(time.time())
    payload = f"{session_id}.{ts}"
    signature = hmac.new(
        GUEST_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def verify_guest_token(token: str) -> Optional[Tuple[str, int]]:
    """
    Validates HMAC signature and timestamp.
    Returns (session_id, timestamp) if valid, else None.
    """
    if not token or not isinstance(token, str):
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    session_id, ts_str, signature = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return None

    now = int(time.time())
    if now - ts > SESSION_LIFETIME_SECONDS + 300 or ts > now + 300:
        return None

    expected_payload = f"{session_id}.{ts}"
    expected_signature = hmac.new(
        GUEST_SECRET.encode("utf-8"),
        expected_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return None

    return session_id, ts


def ensure_guest_user_row(supabase, guest_user_id: str) -> None:
    """Ensures a corresponding row in the user table exists for relational FK integrity."""
    try:
        existing = supabase.table("user").select("id").eq("id", guest_user_id).limit(1).execute()
        if not (existing.data and len(existing.data) > 0):
            supabase.table("user").insert({
                "id": guest_user_id,
                "name": "Guest User",
                "email": f"{guest_user_id}@guest.overbranch.dev",
                "email_verified": False,
                "role": "guest",
            }).execute()
    except Exception as err:
        logger.warning(f"Failed or duplicate insertion of guest user row: {err}")


def get_or_create_guest_session(request: Request) -> Tuple[Dict[str, Any], str, bool]:
    """
    Extracts or establishes a guest session.
    Returns (session_record, signed_token, is_new_session)
    """
    supabase = get_supabase_client()
    fingerprint = compute_device_fingerprint(request)
    now_utc = datetime.now(timezone.utc)

    # Step 1: Check existing cookie
    raw_cookie = request.cookies.get(GUEST_TOKEN_COOKIE_NAME)
    if raw_cookie:
        verified = verify_guest_token(raw_cookie)
        if verified:
            session_id, _ = verified
            res = supabase.table("guest_sessions").select("*").eq("id", session_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                session = res.data[0]
                expires_at = parse_utc_datetime(session["expires_at"])
                if expires_at > now_utc:
                    guest_user_id = f"guest_{session_id}"
                    ensure_guest_user_row(supabase, guest_user_id)
                    return session, raw_cookie, False

    # Step 2: Anti-cookie-clearing check by device fingerprint
    res_fp = supabase.table("guest_sessions").select("*")\
        .eq("fingerprint_hash", fingerprint)\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()

    if res_fp.data and len(res_fp.data) > 0:
        session = res_fp.data[0]
        expires_at = parse_utc_datetime(session["expires_at"])
        if expires_at > now_utc:
            re_signed_token = sign_guest_token(session["id"])
            guest_user_id = f"guest_{session['id']}"
            ensure_guest_user_row(supabase, guest_user_id)
            return session, re_signed_token, False

    # Step 3: Create a new guest session
    new_session_id = str(uuid.uuid4())
    signed_token = sign_guest_token(new_session_id)
    token_hash = hashlib.sha256(signed_token.encode("utf-8")).hexdigest()
    expires_at_dt = now_utc + timedelta(seconds=SESSION_LIFETIME_SECONDS)

    new_session_record = {
        "id": new_session_id,
        "fingerprint_hash": fingerprint,
        "token_hash": token_hash,
        "conversions_used": 0,
        "last_conversion_at": None,
        "created_at": now_utc.isoformat(),
        "expires_at": expires_at_dt.isoformat(),
    }

    supabase.table("guest_sessions").insert(new_session_record).execute()

    guest_user_id = f"guest_{new_session_id}"
    ensure_guest_user_row(supabase, guest_user_id)

    return new_session_record, signed_token, True


def set_guest_cookie(response: Response, token: str, request: Optional[Request] = None) -> None:
    """Sets the secure HttpOnly cookie on the response."""
    is_secure = False
    if request:
        is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    
    if os.getenv("NODE_ENV") == "production" or os.getenv("ENVIRONMENT") == "production":
        is_secure = True

    response.set_cookie(
        key=GUEST_TOKEN_COOKIE_NAME,
        value=token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )
