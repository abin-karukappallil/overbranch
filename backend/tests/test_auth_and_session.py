"""
backend/tests/test_auth_and_session.py — Test Suite for Better Auth & Session Validation
========================================================================================
Validates database connection configuration, models, token extraction,
Better Auth session validation, rate limiting, and endpoint security.
"""

import os
import time
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import Request, HTTPException, status
from fastapi.testclient import TestClient

from database import format_async_database_url
from models import User, Session
from rate_limiter import SlidingWindowRateLimiter, get_client_ip
from auth import (
    extract_session_token,
    extract_guest_token,
    get_current_user,
    get_optional_user,
    get_current_user_or_guest,
    validate_better_auth_session,
)
from main import app


# ============================================================================
# 1. Database Configuration & URL Normalization Tests
# ============================================================================

def test_format_async_database_url_postgresql():
    url = "postgresql://user:pass@localhost:5432/mydb"
    clean_url, connect_args = format_async_database_url(url)
    assert clean_url.startswith("postgresql+asyncpg://")
    assert connect_args.get("statement_cache_size") == 0


def test_format_async_database_url_postgres_prefix():
    url = "postgres://user:pass@localhost:5432/mydb"
    clean_url, connect_args = format_async_database_url(url)
    assert clean_url.startswith("postgresql+asyncpg://")
    assert connect_args.get("statement_cache_size") == 0


def test_format_async_database_url_sslmode():
    url = "postgresql://user:pass@localhost:5432/mydb?sslmode=require"
    clean_url, connect_args = format_async_database_url(url)
    assert "sslmode" not in clean_url
    assert connect_args.get("ssl") is True


# ============================================================================
# 2. ORM Models Tests
# ============================================================================

def test_user_model_serialization():
    user = User(
        id="usr_123",
        name="Alice Researcher",
        email="alice@example.com",
        email_verified=True,
        role="user",
    )
    d = user.to_dict()
    assert d["id"] == "usr_123"
    assert d["name"] == "Alice Researcher"
    assert d["email"] == "alice@example.com"
    assert d["email_verified"] is True
    assert "User(id='usr_123'" in repr(user)


def test_session_model_expiration():
    now_utc = datetime.now(timezone.utc)
    
    # Active session
    future_session = Session(
        id="sess_active",
        token="tok_active_123",
        user_id="usr_123",
        expires_at=now_utc + timedelta(days=7),
    )
    assert future_session.is_expired() is False

    # Expired session
    past_session = Session(
        id="sess_expired",
        token="tok_expired_123",
        user_id="usr_123",
        expires_at=now_utc - timedelta(hours=1),
    )
    assert past_session.is_expired() is True


# ============================================================================
# 3. Token Extraction Tests
# ============================================================================

def test_extract_session_token_from_cookies():
    # 1. Plain better-auth cookie
    req = MagicMock(spec=Request)
    req.cookies = {"better-auth.session_token": "raw_token_xyz"}
    req.headers = {}
    assert extract_session_token(req) == "raw_token_xyz"

    # 2. Signed Better Auth cookie (<token>.<sig>)
    req.cookies = {"better-auth.session_token": "mytoken123.sig_hash_456"}
    assert extract_session_token(req) == "mytoken123"

    # 3. Secure prefix cookie
    req.cookies = {"__Secure-better-auth.session_token": "secure_token.sig"}
    assert extract_session_token(req) == "secure_token"

    # 4. URL-encoded cookie
    req.cookies = {"better-auth.session_token": "token_abc%2Esignature"}
    assert extract_session_token(req) == "token_abc"


def test_extract_session_token_from_headers():
    # Bearer header
    req = MagicMock(spec=Request)
    req.cookies = {}
    req.headers = {"Authorization": "Bearer header_token_123.sig"}
    assert extract_session_token(req) == "header_token_123"

    # Custom header
    req.headers = {"x-auth-token": "custom_header_token"}
    assert extract_session_token(req) == "custom_header_token"

    # None when missing
    req.headers = {}
    assert extract_session_token(req) is None


# ============================================================================
# 4. Sliding Window Rate Limiter Tests
# ============================================================================

@pytest.mark.asyncio
async def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(times=3, seconds=60)
    key = "test_client_ip"

    # First 3 attempts should be allowed
    allowed1, rem1, _ = await limiter.check(key)
    assert allowed1 is True
    assert rem1 == 2

    allowed2, rem2, _ = await limiter.check(key)
    assert allowed2 is True
    assert rem2 == 1

    allowed3, rem3, _ = await limiter.check(key)
    assert allowed3 is True
    assert rem3 == 0

    # 4th attempt should be blocked
    allowed4, rem4, retry_after = await limiter.check(key)
    assert allowed4 is False
    assert rem4 == 0
    assert retry_after > 0


# ============================================================================
# 5. get_current_user Dependency Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_current_user_missing_cookie():
    req = MagicMock(spec=Request)
    req.cookies = {}
    req.headers = {}
    req.url = MagicMock(path="/api/agent/opencode")

    db_mock = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await get_current_user(req, db_mock)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing Better Auth session token" in exc.value.detail


from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    req = MagicMock(spec=Request)
    req.cookies = {"better-auth.session_token": "non_existent_token"}
    req.headers = {}
    req.url = MagicMock(path="/api/agent/opencode")

    # Mock DB query returning None
    db_mock = MagicMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = None
    db_mock.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(req, db_mock)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid or expired session" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_valid_session():
    mock_user = User(id="user_valid_42", email="researcher@overbranch.dev", name="Dr. Euler")
    mock_session = Session(
        id="sess_valid_42",
        token="valid_token_xyz",
        user_id=mock_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    mock_session.user = mock_user

    req = MagicMock(spec=Request)
    req.cookies = {"better-auth.session_token": "valid_token_xyz.signature"}
    req.headers = {}
    req.state = MagicMock()
    req.url = MagicMock(path="/api/agent/opencode")

    db_mock = MagicMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = mock_session
    db_mock.execute = AsyncMock(return_value=execute_result)

    user = await get_current_user(req, db_mock)
    assert user.id == "user_valid_42"
    assert user.email == "researcher@overbranch.dev"


# ============================================================================
# 6. Endpoint Protection Tests (FastAPI TestClient)
# ============================================================================

def test_endpoints_reject_unauthenticated_requests():
    client = TestClient(app)

    # 1. /api/agent/opencode must return 401 without auth
    resp_opencode = client.post(
        "/api/agent/opencode",
        json={"project_id": "test_proj", "user_prompt": "Hello"},
    )
    assert resp_opencode.status_code == status.HTTP_401_UNAUTHORIZED, (
        f"Expected 401 for /api/agent/opencode, got {resp_opencode.status_code}"
    )

    # 2. /api/agent/stop must return 401 without auth
    resp_stop = client.post(
        "/api/agent/stop",
        json={"project_id": "test_proj"},
    )
    assert resp_stop.status_code == status.HTTP_401_UNAUTHORIZED

    # 3. /api/compile must return 401 without session or guest token
    resp_compile = client.post(
        "/api/compile",
        json={"latex_code": r"\documentclass{article}\begin{document}Hi\end{document}"},
    )
    assert resp_compile.status_code == status.HTTP_401_UNAUTHORIZED

    # 4. /api/pdf/convert must return 401 without session
    resp_pdf = client.post(
        "/api/pdf/convert",
        json={"pdf_data": "fake_base64"},
    )
    assert resp_pdf.status_code == status.HTTP_401_UNAUTHORIZED

    # 5. /api/projects/save-file must return 401 without auth
    resp_save = client.post(
        "/api/projects/save-file",
        json={"project_id": "test_proj", "file_path": "main.tex", "raw_code": "% test"},
    )
    assert resp_save.status_code == status.HTTP_401_UNAUTHORIZED

    # 6. /api/health should remain accessible (200 OK)
    resp_health = client.get("/api/health")
    assert resp_health.status_code == status.HTTP_200_OK
    assert resp_health.json()["status"] == "ok"


def test_authenticated_endpoint_with_valid_session():
    client = TestClient(app)
    test_auth_info = {
        "user_id": "test_user_abc",
        "session_id": "sess_123",
        "is_guest": False,
        "authenticated": True,
    }

    # Override dependency to simulate an authenticated Better Auth user
    app.dependency_overrides[get_current_user_or_guest] = lambda: test_auth_info
    try:
        # POST /api/agent/stop with authenticated user
        resp = client.post(
            "/api/agent/stop",
            json={"request_id": "req_123"},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["success"] is True
    finally:
        app.dependency_overrides.pop(get_current_user_or_guest, None)


def test_rate_limiter_blocks_excessive_traffic():
    # Test rate limiter directly on a custom route
    from fastapi import FastAPI, Depends
    from rate_limiter import RateLimiter

    test_app = FastAPI()
    limiter = RateLimiter(times=2, seconds=60, key_prefix="test_rl")

    @test_app.get("/limited", dependencies=[Depends(limiter)])
    def limited_endpoint():
        return {"ok": True}

    client = TestClient(test_app)

    # First 2 requests succeed
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200

    # 3rd request blocked with 429 Too Many Requests
    resp3 = client.get("/limited")
    assert resp3.status_code == 429
    assert "Retry-After" in resp3.headers
    assert "Rate limit exceeded" in resp3.json()["detail"]

