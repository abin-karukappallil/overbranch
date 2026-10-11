"""
multimodal.py — OpenAI-compatible image content parts shared by the LLM providers.

Messages may carry `content` as a list of parts, e.g.
[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}].
Gateways that only accept text get the same message with the image parts removed.
"""

import base64
from typing import Any, Dict, List


def text_part(text: str) -> Dict[str, Any]:
    return {"type": "text", "text": text}


def image_part(data: bytes, mime: str = "image/png") -> Dict[str, Any]:
    b64 = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def has_image_parts(messages: List[Dict[str, Any]]) -> bool:
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in content
        ):
            return True
    return False


IMAGES_OMITTED_NOTE = ("[{n} image(s) that accompanied this message were omitted: this model does not accept "
                       "image input. Work from the text and the measurements given.]")


def strip_image_parts(messages: List[Dict[str, Any]], note: bool = True) -> List[Dict[str, Any]]:
    """
    Returns a copy where list contents keep only their text parts, joined into a string.

    A message that lost images says so (``note``): the text around them was written
    for a reader who could see ("the page image is attached"), and a model told that
    while holding no image either reports that it cannot see or describes one anyway.
    """
    out: List[Dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            dropped = sum(1 for p in content if isinstance(p, dict) and p.get("type") == "image_url")
            if note and dropped:
                texts.append(IMAGES_OMITTED_NOTE.format(n=dropped))
            out.append({**msg, "content": "\n\n".join(t for t in texts if t)})
        else:
            out.append(msg)
    return out
