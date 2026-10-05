"""
Image content parts in the shared Gemini provider: passed through when accepted, retried
text-only (and remembered) when the endpoint rejects them; text-only calls are unchanged.
"""

from providers.base_provider import LLMProviderError
from providers.gemini_provider import GeminiProvider
from providers.multimodal import has_image_parts, image_part, strip_image_parts, text_part

IMG_MSG = [{"role": "user", "content": [text_part("describe"), image_part(b"\x89PNG fake")]}]


def _provider(monkeypatch, fail_with_images):
    p = GeminiProvider()
    seen = []

    def fake_once(messages, *args):
        seen.append(messages)
        if fail_with_images and has_image_parts(messages):
            raise LLMProviderError("All 1 Gemini Web2API keys failed. Last error: bad request", status_code=400,
                                   provider="Gemini")
        return {"content": "ok"}

    monkeypatch.setattr(p, "_chat_once", fake_once)
    return p, seen


def test_image_parts_pass_through_when_accepted(monkeypatch):
    p, seen = _provider(monkeypatch, fail_with_images=False)
    assert p.chat(IMG_MSG, "gemini-3.7-flash")["content"] == "ok"
    assert has_image_parts(seen[0])


def test_rejected_images_retry_text_only_and_are_remembered(monkeypatch):
    p, seen = _provider(monkeypatch, fail_with_images=True)
    assert p.chat(IMG_MSG, "gemini-3.7-flash")["content"] == "ok"
    assert has_image_parts(seen[0]) and seen[1][0]["content"] == "describe"
    p.chat(IMG_MSG, "gemini-3.7-flash")
    assert len(seen) == 3 and not has_image_parts(seen[2])  # no second wasted image attempt


def test_text_messages_unchanged(monkeypatch):
    p, seen = _provider(monkeypatch, fail_with_images=True)
    msgs = [{"role": "user", "content": "plain"}]
    p.chat(msgs, "gemini-3.7-flash")
    assert seen == [msgs]
    assert strip_image_parts(msgs) == msgs
