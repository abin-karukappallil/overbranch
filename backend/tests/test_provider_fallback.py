"""
Provider fallback & OpenRouter key rotation (tests F–J).

No network: the primary provider is a stub and OpenRouter's HTTP call is
replaced with a scripted fake.
"""

import logging
from typing import Any, Dict, List, Optional

import pytest

from cancellation import LLMOperationCancelled
from providers import openrouter_provider as orp
from providers.base_provider import LLMProvider, LLMProviderError
from providers.errors import FailureKind, classify
from providers.key_pool import KeyPool
from providers.router import ProviderRouter

KEYS = [f"sk-or-secret-{i}" for i in range(1, 6)]


class StubPrimary(LLMProvider):
    def __init__(self, error: Optional[Exception] = None):
        self.error = error
        self.calls = 0

    def get_provider_name(self) -> str:
        return "Gemini"

    def get_available_models(self):
        return []

    def chat(self, messages, model, temperature=0.1, max_tokens=4096, api_keys=None, cancel_token=None):
        self.calls += 1
        if self.error:
            raise self.error
        return {"content": "primary", "model_used": model, "finish_reason": "stop", "usage": {}}


class FakeResp:
    def __init__(self, status: int, body: str, headers: Optional[Dict[str, str]] = None):
        self.status_code = status
        self.text = body
        self.headers = headers or {}

    def iter_content(self, chunk_size=4096):
        yield self.text.encode()

    def close(self):
        pass


def ok_body(model: str = "minimax/minimax-m3") -> str:
    return ('{"model": "%s", "choices": [{"message": {"content": "fallback answer"}, '
            '"finish_reason": "stop"}], "usage": {"total_tokens": 7}}' % model)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def router(monkeypatch, clock):
    for i in range(1, 6):
        monkeypatch.delenv(f"OPENROUTER_API_KEY_{i}", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEYS", raising=False)
    monkeypatch.setenv("LLM_FALLBACK_CHAIN", "openrouter:minimax/minimax-m3")
    monkeypatch.setattr(orp, "load_openrouter_keys", lambda: list(KEYS))
    r = ProviderRouter()
    r.openrouter = orp.OpenRouterProvider(pool=KeyPool("openrouter", list(KEYS), clock=clock))
    r._providers["openrouter"] = r.openrouter
    return r


def script(monkeypatch, responses: List[FakeResp], seen: List[Dict[str, Any]]):
    def fake_post(url, headers=None, json=None, stream=None, timeout=None):
        seen.append({"auth": headers["Authorization"], "model": json["model"]})
        return responses.pop(0)
    monkeypatch.setattr(orp.requests, "post", fake_post)


def primary_down(router, status=429):
    stub = StubPrimary(LLMProviderError(f"HTTP {status}", status_code=status, provider="Gemini"))
    router.gemini = stub
    router._providers["gemini"] = stub
    return stub


# --- F / G ------------------------------------------------------------------

def test_primary_success_does_not_touch_fallback(router, monkeypatch):
    stub = StubPrimary()
    router.gemini = stub
    router._providers["gemini"] = stub
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [], seen)
    resp = router.chat([{"role": "user", "content": "hi"}], model="gemini-3.7-flash")
    assert resp["content"] == "primary"
    assert resp["is_fallback"] is False
    assert seen == []


@pytest.mark.parametrize("status", [429, 402, 503, 504])
def test_primary_failure_falls_back_to_openrouter_minimax_m3(router, monkeypatch, status):
    primary_down(router, status)
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [FakeResp(200, ok_body())], seen)
    resp = router.chat([{"role": "user", "content": "hi"}], model="gemini-3.7-flash")
    assert resp["content"] == "fallback answer"
    assert resp["is_fallback"] is True
    assert resp["provider"] == "openrouter"
    assert seen[0]["model"] == "minimax/minimax-m3"
    assert resp["key_id"] == "openrouter#1"
    assert [a["ok"] for a in resp["attempts"]] == [False, True]


def test_timeout_exception_falls_back(router, monkeypatch):
    stub = StubPrimary(TimeoutError("Request timed out"))
    router.gemini = stub
    router._providers["gemini"] = stub
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [FakeResp(200, ok_body())], seen)
    assert router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")["is_fallback"]


def test_no_fallback_on_bad_request_or_cancel(router, monkeypatch):
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [], seen)
    stub = StubPrimary(LLMProviderError("HTTP 400: invalid messages", status_code=400))
    router.gemini = stub
    router._providers["gemini"] = stub
    with pytest.raises(LLMProviderError):
        router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    stub.error = LLMOperationCancelled()
    with pytest.raises(LLMOperationCancelled):
        router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    assert seen == []


# --- H / I / J ---------------------------------------------------------------

def test_429_rotates_to_next_key_and_sticks(router, monkeypatch):
    primary_down(router)
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [FakeResp(429, '{"error":"rate limit"}'), FakeResp(200, ok_body()),
                         FakeResp(200, ok_body())], seen)
    resp = router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    assert resp["key_id"] == "openrouter#2"
    assert [s["auth"] for s in seen] == [f"Bearer {KEYS[0]}", f"Bearer {KEYS[1]}"]
    # Sticky: the next request starts on key 2, it does not rotate unnecessarily.
    router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    assert seen[-1]["auth"] == f"Bearer {KEYS[1]}"
    states = {s["key_id"]: s for s in router.openrouter.pool.snapshot()}
    assert states["openrouter#1"]["status"] == "cooling_down"
    assert states["openrouter#1"]["last_failure"] == "rate_limit"


def test_all_five_keys_rate_limited_raises_provider_failure(router, monkeypatch):
    primary_down(router)
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [FakeResp(429, "rate limit") for _ in range(5)], seen)
    with pytest.raises(LLMProviderError) as exc:
        router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    assert len(seen) == 5
    assert {s["auth"] for s in seen} == {f"Bearer {k}" for k in KEYS}
    assert exc.value.kind == FailureKind.RATE_LIMIT


def test_key_recovers_after_cooldown(router, monkeypatch, clock):
    primary_down(router)
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [FakeResp(429, "x", {"Retry-After": "20"}), FakeResp(200, ok_body())], seen)
    router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    pool = router.openrouter.pool
    assert [lease.key_id for lease in pool.candidates()][0] == "openrouter#2"
    assert "openrouter#1" not in [lease.key_id for lease in pool.candidates()]
    clock.t += 21  # Retry-After honoured
    assert "openrouter#1" in [lease.key_id for lease in pool.candidates()]
    assert {s["key_id"]: s for s in pool.snapshot()}["openrouter#1"]["status"] == "healthy"


def test_quota_and_auth_cool_down_longer_than_rate_limit(clock):
    pool = KeyPool("openrouter", KEYS[:3], clock=clock)
    assert pool.report_failure("openrouter#1", FailureKind.RATE_LIMIT) == 30
    assert pool.report_failure("openrouter#1", FailureKind.RATE_LIMIT) == 60  # exponential
    assert pool.report_failure("openrouter#2", FailureKind.QUOTA) == 3600
    assert pool.report_failure("openrouter#3", FailureKind.AUTH) > 3600
    assert pool.report_failure("openrouter#3", FailureKind.BAD_REQUEST) == 0


def test_every_key_cooling_down_still_offers_the_soonest(clock):
    pool = KeyPool("openrouter", KEYS[:2], clock=clock)
    pool.report_failure("openrouter#1", FailureKind.QUOTA)
    pool.report_failure("openrouter#2", FailureKind.RATE_LIMIT)
    assert [lease.key_id for lease in pool.candidates()] == ["openrouter#2"]


def test_bad_request_does_not_burn_other_keys(router, monkeypatch):
    primary_down(router)
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [FakeResp(400, '{"error": "bad"}')], seen)
    with pytest.raises(LLMProviderError):
        router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    assert len(seen) == 1


# --- secrets ----------------------------------------------------------------

def test_keys_never_appear_in_response_snapshot_or_logs(router, monkeypatch, caplog):
    primary_down(router)
    seen: List[Dict[str, Any]] = []
    script(monkeypatch, [FakeResp(429, "rate limit"), FakeResp(200, ok_body())], seen)
    with caplog.at_level(logging.DEBUG):
        resp = router.chat([{"role": "user", "content": "x"}], model="gemini-3.7-flash")
    blob = repr(resp) + repr(router.openrouter.pool.snapshot()) + repr(router.openrouter.candidates) + caplog.text
    for k in KEYS:
        assert k not in blob


def test_minimax_m3_aliases_do_not_map_to_text_01(router):
    for alias in ("MiniMax M3", "minimax-m3", "minimax"):
        assert router.openrouter._normalize_model_name(alias) == "minimax/minimax-m3"
    assert router.get_fallback_model() == "minimax/minimax-m3"


def test_classify_text_and_status():
    assert classify(None, "Resource_Exhausted")[0] == FailureKind.RATE_LIMIT
    assert classify(404, "model not found")[0] == FailureKind.MODEL_UNAVAILABLE
    assert classify(429, '{"retry_after": 12}') == (FailureKind.RATE_LIMIT, 12.0)
