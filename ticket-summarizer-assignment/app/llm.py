import hashlib
import json
from typing import Any, Protocol, Sequence

from . import config

_PROMPT = (
    "You are a support-ticket summarizer (prompt {version}). Summarize the ticket "
    "in the '{style}' style. Reply with a JSON object containing exactly these "
    "fields: summary (string), key_points (array of strings), sentiment (one of "
    "positive/neutral/negative). Ticket:\n\n{text}"
)


def _stable_bucket(text: str, mod: int) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest, 16) % mod


def _parse(raw: str) -> dict:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(text)


def _text_from_content(content: Sequence[Any]) -> str:
    """Collect text from Anthropic content blocks; ignore non-text blocks."""
    parts: list[str] = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type is None and isinstance(block, dict):
            block_type = block.get("type")
            text = block.get("text")
        else:
            text = getattr(block, "text", None)

        if block_type == "text" and text:
            parts.append(text)

    if not parts:
        raise ValueError("Anthropic response contained no text blocks")
    return "\n".join(parts)


class LLMProvider(Protocol):
    async def summarize(self, text: str, style: str = "brief") -> dict: ...


class MockProvider:

    async def summarize(self, text: str, style: str = "brief") -> dict:
        version = config.PROMPT_VERSION
        sentiment = "negative" if "angry" in text.lower() else "neutral"

        if style == "detailed":
            payload = {
                "summary": f"[{version}] Detailed summary of a {len(text)}-char ticket "
                           f"covering the customer's reported problem and context.",
                "key_points": [
                    "Customer described the issue in detail",
                    "Impact and context captured",
                    "Awaiting triage and follow-up",
                ],
                "sentiment": sentiment,
            }
        else:
            payload = {
                "summary": f"[{version}] Brief summary ({len(text)} chars).",
                "key_points": ["Issue reported by customer"],
                "sentiment": sentiment,
            }

        body = json.dumps(payload)

        if _stable_bucket(text, 3) == 0:
            raw = f"Sure! Here's the summary:\n```json\n{body}\n```"
        else:
            raw = body

        return _parse(raw)


class AnthropicProvider:
    def __init__(self) -> None:
        from anthropic import AsyncAnthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    async def summarize(self, text: str, style: str = "brief") -> dict:
        # Braces inside `text` are fine: .format only expands fields in the
        # template; substituted values are not re-parsed.
        prompt = _PROMPT.format(version=config.PROMPT_VERSION, style=style, text=text)
        msg = await self._client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _text_from_content(msg.content)
        return _parse(raw)


def get_provider() -> LLMProvider:
    if config.LLM_PROVIDER == "anthropic":
        return AnthropicProvider()
    return MockProvider()
