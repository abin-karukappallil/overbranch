"""
Strict Web2API gateway chain.

Every request tries the gateways in WEB2API_GATEWAYS order, cycles the whole chain
LLM_CHAIN_CYCLES times, and never touches OpenRouter / Groq / NVIDIA. Exhaustion is
reported as "Model outage — please retry." and nothing else.

No external network: gateways are stubs, or tiny local HTTP servers for the
liveness (idle stream) tests.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

import pytest

from cancellation import CancellationToken, LLMOperationCancelled
from providers.base_provider import LLMProvider, LLMProviderError
from providers.errors import OUTAGE_MESSAGE, FailureKind, classify, classify_exception, outage_retrying
from providers.router import CYCLE_BACKOFF_SECONDS, DEFAULT_MODEL, ProviderRouter

GATEWAY_URLS = [
    "https://g1.overbranch.app/v1",
    "https://g2.overbranch.app/v1",
    "https://g3.overbranch.app/v1",
    "https://g4.overbranch.app/v1",
    "https://g5.overbranch.app/v1",
    "https://model.overbranch.app/v1",
    "https://overmodel.abinthomas.dev/v1",
]
NAMES = ["G1", "G2", "G3", "G4", "G5", "MODEL", "OVERMODEL"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "WEB2API_GATEWAYS", "WEB2API_API_KEY", "WEB2API_API_KEYS", "LLM_CHAIN_CYCLES",
        "GEMINI_WEB2API_BASE_URL", "GEMINI_WEB2API_API_KEY", "GEMINI2_WEB2API_BASE_URL",
        "GEMINI2_WEB2API_API_KEY", "LLM_ATTEMPT_WALL_CAP", "LLM_GATEWAY_COOLDOWN", "LLM_IDLE_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)
    for i in range(1, 6):
        for ns in ("GEMINI", "GEMINI2"):
            monkeypatch.delenv(f"{ns}_WEB2API_API_KEY_{i}", raising=False)


def err(status: Optional[int], msg: str = "boom", kind: Optional[FailureKind] = None) -> LLMProviderError:
    return LLMProviderError(msg, status_code=status, provider="stub", kind=kind)


class StubGateway(LLMProvider):
    """Answers, or raises, according to ``outcomes`` (the last one repeats)."""

    supports_images = True

    def __init__(self, name: str, log: List[str], outcomes: Optional[List[Any]] = None):
        self.name = name
        self.log = log
        self.outcomes = outcomes if outcomes is not None else [None]
        self.calls = 0

    def get_provider_name(self) -> str:
        return self.name

    def get_available_models(self):
        return []

    def chat(self, messages, model, temperature=0.1, max_tokens=4096, api_keys=None, cancel_token=None):
        self.log.append(self.name)
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome(self, messages, model)
        return {"content": f"answer from {self.name}", "model_used": model, "finish_reason": "stop", "usage": {}}


class Harness:
    def __init__(self, router: ProviderRouter, gateways: List[StubGateway], log: List[str]):
        self.router, self.gateways, self.log = router, gateways, log
        self.sleeps: List[float] = []
        self.now = 1000.0

    def chat(self, **kw):
        kw.setdefault("messages", [{"role": "user", "content": "hi"}])
        kw.setdefault("model", DEFAULT_MODEL)
        return self.router.chat(**kw)


def make(outcomes: Optional[Dict[str, List[Any]]] = None, names: List[str] = NAMES) -> Harness:
    outcomes = outcomes or {}
    log: List[str] = []
    gateways = [StubGateway(n, log, outcomes.get(n)) for n in names]
    router = ProviderRouter()
    router.set_gateway_chain([(g.name, g) for g in gateways])
    h = Harness(router, gateways, log)
    router._clock = lambda: h.now

    def fake_sleep(seconds: float) -> None:
        h.sleeps.append(seconds)
        h.now += seconds

    router._sleep = fake_sleep
    return h


def all_down(status: int = 503) -> Dict[str, List[Any]]:
    return {n: [err(status)] for n in NAMES}


# --- configuration ------------------------------------------------------------

def test_chain_is_built_from_web2api_gateways_in_order(monkeypatch):
    monkeypatch.setenv("WEB2API_GATEWAYS", ",".join(GATEWAY_URLS))
    monkeypatch.setenv("WEB2API_API_KEY", "shared-key")
    router = ProviderRouter()
    chain = router.fallback_chain("gemini-3.7-flash")
    assert [n for n, _, _ in chain] == NAMES
    assert [p.base_url for _, p, _ in chain] == GATEWAY_URLS
    # one provider instance per gateway, all on the shared key
    assert len({id(p) for _, p, _ in chain}) == 7
    assert all([k["key"] for k in p.candidates] == ["shared-key"] for _, p, _ in chain)


def test_gateways_without_the_shared_key_are_not_in_the_chain(monkeypatch):
    monkeypatch.setenv("WEB2API_GATEWAYS", ",".join(GATEWAY_URLS))
    assert ProviderRouter().fallback_chain("gemini-3.7-flash") == []


def test_legacy_gemini_vars_still_build_a_chain(monkeypatch):
    monkeypatch.setenv("GEMINI_WEB2API_BASE_URL", "https://one.example/v1")
    monkeypatch.setenv("GEMINI_WEB2API_API_KEY", "k1")
    monkeypatch.setenv("GEMINI2_WEB2API_BASE_URL", "https://two.example/v1")
    monkeypatch.setenv("GEMINI2_WEB2API_API_KEY", "k2")
    chain = ProviderRouter().fallback_chain("gemini-3.7-flash")
    assert [n for n, _, _ in chain] == ["GEMINI", "GEMINI2"]
    assert [p.base_url for _, p, _ in chain] == ["https://one.example/v1", "https://two.example/v1"]


def test_available_models_are_gateway_models_only(monkeypatch):
    models = ProviderRouter().get_available_models()
    assert [p["name"] for p in models["providers"]] == ["Gemini Web2API"]
    ids = [m["id"] for m in models["providers"][0]["models"]]
    assert ids and all(i.startswith("gemini-") for i in ids)
    assert models["default_model"] == DEFAULT_MODEL


def test_every_model_name_routes_to_the_chain_with_a_gateway_model():
    h = make()
    for requested in ("llama-3.1-8b-instant", "minimax/minimax-m3", "openai/gpt-oss-120b", "auto:smart", ""):
        chain = h.router.fallback_chain(requested)
        assert [n for n, _, _ in chain] == NAMES
        assert {m for _, _, m in chain} == {DEFAULT_MODEL}
    assert {m for _, _, m in h.router.fallback_chain("gemini-3.5-flash")} == {"gemini-3.5-flash"}


# --- order, cycles, backoff ----------------------------------------------------

def test_first_gateway_answers_and_nothing_else_is_called():
    h = make()
    resp = h.chat()
    assert resp["content"] == "answer from G1" and resp["provider"] == "G1"
    assert resp["is_fallback"] is False
    assert h.log == ["G1"]


def test_gateways_are_tried_in_order_until_one_answers():
    h = make({n: [err(503)] for n in NAMES[:5]})
    resp = h.chat()
    assert h.log == NAMES[:6]
    assert resp["provider"] == "MODEL" and resp["is_fallback"] is True
    assert [a["ok"] for a in resp["attempts"]] == [False] * 5 + [True]
    assert [a["provider"] for a in resp["attempts"]] == NAMES[:6]


def test_last_gateway_is_the_last_resort():
    h = make({n: [err(504)] for n in NAMES[:-1]})
    assert h.chat()["provider"] == "OVERMODEL"
    assert h.log == NAMES


def test_whole_chain_is_cycled_twelve_times_then_outage():
    h = make(all_down(503))
    with pytest.raises(LLMProviderError) as ei:
        h.chat()
    assert len(h.log) == 7 * 12
    # strictly g1..overmodel, repeated
    assert h.log == NAMES * 12
    assert str(ei.value) == OUTAGE_MESSAGE == "Model outage — please retry."
    assert len(ei.value.attempts) == 84
    assert list(CYCLE_BACKOFF_SECONDS) == [1.0, 2.0, 4.0, 8.0, 15.0]


def test_backoff_between_cycles_is_1_2_4_8_15_then_15():
    h = make(all_down(503))
    waits: List[float] = []

    def record_wait(seconds: float, cancel_token) -> None:
        waits.append(seconds)
        h.now += seconds

    h.router._wait = record_wait
    with pytest.raises(LLMProviderError):
        h.chat()
    assert waits == [1.0, 2.0, 4.0, 8.0] + [15.0] * 7  # 11 gaps between 12 cycles


def test_real_wait_is_sliced_so_cancellation_is_noticed():
    h = make()
    slices: List[float] = []
    h.router._sleep = slices.append
    h.router._wait(1.0, None)
    assert slices == [0.25] * 4


def test_cycles_follow_llm_chain_cycles(monkeypatch):
    monkeypatch.setenv("LLM_CHAIN_CYCLES", "3")
    h = make(all_down(503))
    with pytest.raises(LLMProviderError):
        h.chat()
    assert h.log == NAMES * 3


def test_a_later_cycle_can_still_succeed():
    # G1 fails the first cycle only; every other gateway is always down.
    outcomes = {n: [err(503)] for n in NAMES}
    outcomes["G1"] = [err(503), None]
    h = make(outcomes)
    resp = h.chat()
    assert h.log == NAMES + ["G1"]
    assert resp["provider"] == "G1" and resp["is_fallback"] is True
    assert h.sleeps and sum(h.sleeps) == pytest.approx(1.0)


def test_allow_fallback_false_is_a_single_pass_without_backoff():
    h = make(all_down(503))
    with pytest.raises(LLMProviderError) as ei:
        h.chat(allow_fallback=False)
    assert h.log == NAMES
    assert h.sleeps == []
    assert str(ei.value) == OUTAGE_MESSAGE


def test_observer_gets_attempt_numbers_for_the_retry_status_line():
    h = make({"G1": [err(503)]})
    seen: List[Dict[str, Any]] = []
    h.chat(observer=seen.append)
    first = seen[0]
    assert first["ok"] is False and first["will_retry"] is True
    assert first["attempt"] == 1 and first["total"] == 84 and first["cycles"] == 12
    assert outage_retrying(first["attempt"] + 1, first["total"]) == "Model outage — retrying (2/84)…"
    assert seen[-1]["ok"] is True and seen[-1]["will_retry"] is False


def test_final_failed_attempt_is_not_marked_will_retry():
    h = make(all_down(503))
    seen: List[Dict[str, Any]] = []
    with pytest.raises(LLMProviderError):
        h.chat(observer=seen.append)
    assert [a["will_retry"] for a in seen[:-1]] == [True] * 83
    assert seen[-1]["will_retry"] is False


# --- no other provider, ever ---------------------------------------------------

def test_openrouter_groq_nvidia_are_never_called(monkeypatch):
    import requests

    def forbidden(*a, **kw):
        raise AssertionError(f"a non-gateway provider was called: {a[:1]}")

    monkeypatch.setattr(requests, "post", forbidden)
    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setenv("OPENROUTER_API_KEY_1", "sk-or-1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-1")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-1")
    monkeypatch.setenv("LLM_FALLBACK_CHAIN", "openrouter:minimax/minimax-m3,nvidia:z-ai/glm-5.3")
    h = make(all_down(503))
    with pytest.raises(LLMProviderError) as ei:
        h.chat(model="minimax/minimax-m3")
    assert {a["provider"] for a in ei.value.attempts} == set(NAMES)
    assert not hasattr(h.router, "openrouter") and not hasattr(h.router, "groq") and not hasattr(h.router, "nvidia")
    assert {n for n, _, _ in h.router.fallback_chain("llama-3.1-8b-instant")} == set(NAMES)


def test_chat_json_and_fast_tier_use_the_same_chain():
    h = make({"G1": [err(503)]})
    assert h.router.chat_fast_tier([{"role": "user", "content": "x"}])["provider"] == "G2"

    ok = '{"a": 1}'
    h2 = make({"G1": [lambda g, m, mod: {"content": ok, "model_used": mod, "finish_reason": "stop", "usage": {}}]})
    from providers.router import TaskType
    assert h2.router.chat_json_with_retry([{"role": "user", "content": "x"}], TaskType.TASK_CLASSIFICATION, ["a"]) == {"a": 1}
    assert h2.log == ["G1"]


# --- 30s cooldown --------------------------------------------------------------

def test_a_gateway_that_timed_out_is_skipped_for_30_seconds():
    h = make({"G1": [err(504, "timed out", FailureKind.TIMEOUT), None]})
    first = h.chat()
    assert first["provider"] == "G2"
    assert h.log == ["G1", "G2"]

    h.log.clear()
    h.now += 10  # still cooling
    second = h.chat()
    assert second["provider"] == "G2"
    assert h.log == ["G2"], "G1 must be skipped while cooling"

    h.log.clear()
    h.now += 25  # 35s after the failure: cooled down
    third = h.chat()
    assert h.log == ["G1"] and third["provider"] == "G1"


def test_5xx_starts_a_cooldown_but_429_does_not():
    h = make({"G1": [err(500)], "G2": [err(429)]})
    h.chat()
    h.log.clear()
    h.chat()
    assert h.log[0] == "G2"  # G1 cooling, G2 (429) is not


def test_when_every_gateway_is_cooling_all_of_them_are_tried():
    h = make(all_down(503))
    with pytest.raises(LLMProviderError):
        h.chat(allow_fallback=False)
    assert h.log == NAMES
    h.log.clear()
    # all seven are cooling now; a new call must still walk the full chain, in order
    with pytest.raises(LLMProviderError):
        h.chat(allow_fallback=False)
    assert h.log == NAMES


def test_cooldown_does_not_skip_in_the_first_cycle_of_a_fresh_request_when_all_are_healthy():
    h = make()
    h.chat()
    h.chat()
    assert h.log == ["G1", "G1"]


def test_success_clears_a_cooldown():
    h = make({"G1": [err(503), None]})
    h.chat()
    h.now += 31
    h.log.clear()
    assert h.chat()["provider"] == "G1"
    h.log.clear()
    assert h.chat()["provider"] == "G1"  # healthy again, no residual cooldown


# --- 400 -----------------------------------------------------------------------

def test_bad_request_advances_but_stops_cycling_after_one_pass():
    h = make({n: [err(400, "invalid messages")] for n in NAMES})
    with pytest.raises(LLMProviderError) as ei:
        h.chat()
    assert h.log == NAMES, "one full pass, then stop"
    assert h.sleeps == []
    assert str(ei.value) == OUTAGE_MESSAGE
    assert ei.value.kind == FailureKind.BAD_REQUEST


def test_bad_request_on_one_gateway_still_lets_the_next_answer():
    h = make({"G1": [err(400, "nope")]})
    assert h.chat()["provider"] == "G2"


def test_a_400_mid_pass_ends_the_run_after_that_pass():
    outcomes = {n: [err(503)] for n in NAMES}
    outcomes["G3"] = [err(400)]
    h = make(outcomes)
    with pytest.raises(LLMProviderError):
        h.chat()
    assert h.log == NAMES


# --- cancellation --------------------------------------------------------------

def test_cancellation_is_raised_immediately():
    h = make({"G1": [LLMOperationCancelled()]})
    with pytest.raises(LLMOperationCancelled):
        h.chat()
    assert h.log == ["G1"]


def test_cancelled_token_stops_before_any_call():
    h = make()
    tok = CancellationToken("t")
    tok.cancel("stop")
    with pytest.raises(LLMOperationCancelled):
        h.chat(cancel_token=tok)
    assert h.log == []


def test_cancellation_during_the_backoff_is_honoured():
    h = make(all_down(503))
    tok = CancellationToken("t")
    real_sleep = h.router._sleep

    def sleep_then_cancel(seconds: float) -> None:
        real_sleep(seconds)
        tok.cancel("user stop")

    h.router._sleep = sleep_then_cancel
    with pytest.raises(LLMOperationCancelled):
        h.chat(cancel_token=tok)
    assert h.log == NAMES  # one cycle, then cancelled in the first back-off


# --- timeouts: liveness, not deadlines -------------------------------------------

def test_an_attempt_is_capped_by_the_wall_clock(monkeypatch):
    monkeypatch.setenv("LLM_ATTEMPT_WALL_CAP", "0.2")
    release = threading.Event()
    seen_tokens: List[Any] = []

    def hang(gw, messages, model):
        release.wait(5)
        return {"content": "late", "model_used": model, "finish_reason": "stop", "usage": {}}

    class Tracking(StubGateway):
        def chat(self, messages, model, temperature=0.1, max_tokens=4096, api_keys=None, cancel_token=None):
            seen_tokens.append(cancel_token)
            return super().chat(messages, model, temperature, max_tokens, api_keys, cancel_token)

    log: List[str] = []
    g1, g2 = Tracking("G1", log, [hang]), StubGateway("G2", log)
    router = ProviderRouter()
    router.set_gateway_chain([("G1", g1), ("G2", g2)])
    try:
        resp = router.chat([{"role": "user", "content": "x"}], DEFAULT_MODEL)
    finally:
        release.set()
    assert resp["provider"] == "G2"
    assert resp["attempts"][0]["failure"] == FailureKind.TIMEOUT.value
    # the abandoned attempt was told to stop
    assert seen_tokens[0].is_cancelled()


def test_final_attempt_is_bounded_too(monkeypatch):
    monkeypatch.setenv("LLM_ATTEMPT_WALL_CAP", "0.2")
    release = threading.Event()

    def hang(gw, messages, model):
        release.wait(5)

    log: List[str] = []
    router = ProviderRouter()
    router.set_gateway_chain([("G1", StubGateway("G1", log, [hang]))])
    router._sleep = lambda s: None
    monkeypatch.setenv("LLM_CHAIN_CYCLES", "1")
    t0 = time.time()
    try:
        with pytest.raises(LLMProviderError) as ei:
            router.chat([{"role": "user", "content": "x"}], DEFAULT_MODEL)
    finally:
        release.set()
    assert time.time() - t0 < 3
    assert str(ei.value) == OUTAGE_MESSAGE


class _GatewayServer:
    """A local OpenAI-style streaming endpoint with a scripted behaviour."""

    def __init__(self, behaviour: str):
        self.behaviour = behaviour
        self.requests = 0
        self.stop = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_POST(self):
                outer.requests += 1
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                if outer.behaviour == "503":
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error": "down"}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def chunk(text, finish=None):
                    payload = {"id": "c", "object": "chat.completion.chunk", "created": 0,
                               "model": "gemini-3.7-flash",
                               "choices": [{"index": 0, "delta": {"content": text} if text else {},
                                            "finish_reason": finish}]}
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                    self.wfile.flush()

                if outer.behaviour == "stall":
                    chunk("par")
                    outer.stop.wait(10)  # then silence: an idle stream
                    return
                if outer.behaviour == "slow":
                    for word in ["one ", "two ", "three ", "four ", "five "]:
                        chunk(word)
                        time.sleep(0.3)  # every gap < idle timeout, whole answer > idle timeout
                    chunk("", "stop")
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                chunk("ok")
                chunk("", "stop")
                self.wfile.write(b"data: [DONE]\n\n")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def servers():
    made: List[_GatewayServer] = []

    def make_server(behaviour: str) -> _GatewayServer:
        s = _GatewayServer(behaviour)
        made.append(s)
        return s

    yield make_server
    for s in made:
        s.close()


def test_an_idle_stream_fails_over_to_the_next_gateway(monkeypatch, servers):
    stalled, healthy = servers("stall"), servers("ok")
    monkeypatch.setenv("WEB2API_GATEWAYS", f"{stalled.url},{healthy.url}")
    monkeypatch.setenv("WEB2API_API_KEY", "k")
    monkeypatch.setenv("LLM_IDLE_TIMEOUT", "1")
    router = ProviderRouter()
    import openai  # noqa: F401 — the SDK's first import is slow; keep it out of the timing below
    t0 = time.time()
    resp = router.chat([{"role": "user", "content": "hi"}], DEFAULT_MODEL)
    assert resp["content"] == "ok"
    assert resp["attempts"][0]["ok"] is False
    assert resp["attempts"][0]["failure"] == FailureKind.TIMEOUT.value
    assert resp["is_fallback"] is True
    assert time.time() - t0 < 6, "the stalled gateway must be given up on at the idle timeout, not waited out"
    assert stalled.requests == 1 and healthy.requests == 1


def test_a_slow_but_streaming_answer_is_not_cut_off(monkeypatch, servers):
    slow, healthy = servers("slow"), servers("ok")
    monkeypatch.setenv("WEB2API_GATEWAYS", f"{slow.url},{healthy.url}")
    monkeypatch.setenv("WEB2API_API_KEY", "k")
    monkeypatch.setenv("LLM_IDLE_TIMEOUT", "1")  # whole answer takes ~1.5s+, each gap is 0.3s
    router = ProviderRouter()
    resp = router.chat([{"role": "user", "content": "hi"}], DEFAULT_MODEL)
    assert resp["content"] == "one two three four five "
    assert resp["is_fallback"] is False
    assert healthy.requests == 0


def test_http_5xx_from_a_real_gateway_falls_over_and_cools_down(monkeypatch, servers):
    down, healthy = servers("503"), servers("ok")
    monkeypatch.setenv("WEB2API_GATEWAYS", f"{down.url},{healthy.url}")
    monkeypatch.setenv("WEB2API_API_KEY", "k")
    router = ProviderRouter()
    assert router.chat([{"role": "user", "content": "hi"}], DEFAULT_MODEL)["content"] == "ok"
    assert down.requests == 1
    router.chat([{"role": "user", "content": "hi"}], DEFAULT_MODEL)
    assert down.requests == 1, "cooling gateway is skipped"
    assert healthy.requests == 2


# --- failure classification -------------------------------------------------------

def test_classify_text_and_status():
    assert classify(None, "Resource_Exhausted")[0] == FailureKind.RATE_LIMIT
    assert classify(404, "model not found")[0] == FailureKind.MODEL_UNAVAILABLE
    assert classify(429, '{"retry_after": 12}') == (FailureKind.RATE_LIMIT, 12.0)


def test_transport_errors_are_classified_without_relying_on_text():
    import httpx

    assert classify_exception(httpx.ReadTimeout(""))[0] == FailureKind.TIMEOUT
    assert classify_exception(httpx.ConnectError("[Errno 111]"))[0] == FailureKind.UNAVAILABLE
    assert classify_exception(TimeoutError())[0] == FailureKind.TIMEOUT


# --- callers go through the chain ---------------------------------------------------

def test_pdf2latex_uses_the_full_chain(monkeypatch):
    """allow_fallback=True is the contract: a page call walks and cycles the whole chain."""
    from pdf2latex.llm import _chat
    from providers.router import provider_router

    captured_kwargs: Dict[str, Any] = {}

    def fake_chat(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {"content": "latex body"}

    monkeypatch.setattr(provider_router, "chat", fake_chat)
    res = _chat([{"role": "user", "content": "test"}], max_tokens=1000, token=CancellationToken("test"))
    assert res == "latex body"
    assert captured_kwargs.get("allow_fallback") is True
    assert captured_kwargs.get("model") == DEFAULT_MODEL


def test_pdf2latex_llm_available_follows_the_gateway_config(monkeypatch):
    from pdf2latex.llm import llm_available

    assert llm_available() is False
    monkeypatch.setenv("WEB2API_GATEWAYS", GATEWAY_URLS[0])
    assert llm_available() is False  # URL but no key
    monkeypatch.setenv("WEB2API_API_KEY", "k")
    assert llm_available() is True


def test_pdf2latex_does_not_nest_retries_on_top_of_the_chain(monkeypatch):
    import asyncio

    from pdf2latex import llm
    from providers.router import provider_router

    monkeypatch.setenv("WEB2API_GATEWAYS", GATEWAY_URLS[0])
    monkeypatch.setenv("WEB2API_API_KEY", "k")
    calls = {"n": 0}

    def failing(messages, max_tokens, token):
        calls["n"] += 1
        raise LLMProviderError(OUTAGE_MESSAGE)

    monkeypatch.setattr(llm, "_chat", failing)
    with pytest.raises(llm.LLMCallFailed):
        asyncio.run(llm.complete("sys", "user", timeout=30, retries=2, concurrency=1))
    assert provider_router.chain_active()
    assert calls["n"] == 1


def test_file_analyzer_streams_through_the_chain_and_keeps_its_sse_shape(monkeypatch, tmp_path):
    import file_analyzer
    from providers.router import provider_router

    seen: Dict[str, Any] = {}

    def fake_chat(messages, model, **kw):
        seen["model"] = model
        seen["kw"] = kw
        return {"content": "x" * 900, "usage": {"prompt_tokens": 3}, "provider": "G2"}

    monkeypatch.setattr(provider_router, "chat", fake_chat)
    f = tmp_path / "a.txt"
    f.write_text("hello")
    provider = file_analyzer.GPT120BFileAnalysisProvider()
    events = [e for e in provider.analyze_file_stream(str(f), "a.txt", "text/plain", "what is this?")
              if e.startswith("data: ")]
    payloads = [json.loads(e[6:]) for e in events]
    assert [p.get("chunk") for p in payloads[:-1]] == ["x" * 400, "x" * 400, "x" * 100]
    assert payloads[-1] == {"done": True, "filename": "a.txt", "mimeType": "text/plain"}
    assert seen["model"] == DEFAULT_MODEL

    result = provider.analyze_file(str(f), "a.txt", "text/plain", "what is this?")
    assert result.analysis == "x" * 900 and result.usage["promptTokens"] == 3


def test_file_analyzer_reports_only_the_outage_message(monkeypatch, tmp_path):
    import file_analyzer
    from fastapi import HTTPException
    from providers.router import provider_router

    def boom(*a, **kw):
        raise LLMProviderError("G1 HTTP 503 secret detail", status_code=503)

    monkeypatch.setattr(provider_router, "chat", boom)
    f = tmp_path / "a.txt"
    f.write_text("hello")
    provider = file_analyzer.GPT120BFileAnalysisProvider()
    events = [json.loads(e[6:]) for e in provider.analyze_file_stream(str(f), "a.txt", "text/plain", "q")
              if e.startswith("data: ")]
    assert events == [{"error": True, "detail": OUTAGE_MESSAGE}]
    with pytest.raises(HTTPException) as ei:
        provider.analyze_file(str(f), "a.txt", "text/plain", "q")
    assert ei.value.detail == OUTAGE_MESSAGE


def test_file_analyzer_has_no_direct_http_to_other_providers():
    import inspect

    import file_analyzer

    src = inspect.getsource(file_analyzer)
    for needle in ("api.groq.com", "integrate.api.nvidia.com", "FREELLM", "requests.post"):
        assert needle not in src.replace("FreeLLM, OpenRouter", "")


def test_agent_failure_wording_is_the_outage_message():
    from agent.agent_loop import _friendly_llm_error

    for e in (err(429), err(504, "timed out"), err(400), err(None, "weird"), RuntimeError("x")):
        e.attempts = [{"provider": "G1", "failure": "timeout"}]
        assert _friendly_llm_error(e) == OUTAGE_MESSAGE
