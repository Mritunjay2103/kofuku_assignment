from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.llm import (
    MockProvider,
    _PROMPT,
    _parse,
    _stable_bucket,
    _text_from_content,
)
from app.main import _points_from, _to_response, app
from app.ratelimit import RateLimiter

client = TestClient(app)

AUTH = {"X-API-Key": "demo-key-alice"}
AUTH_BOB = {"X-API-Key": "demo-key-bob"}


def _text_in_bucket(target: int, prefix: str = "ticket") -> str:
    """Find a ticket string that lands in the mock markdown bucket."""
    for i in range(10_000):
        text = f"{prefix}-{i}"
        if _stable_bucket(text, 3) == target:
            return text
    raise RuntimeError(f"no text found for bucket {target}")


# --- health / auth -----------------------------------------------------------


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_summarize_requires_api_key():
    r = client.post("/summarize", json={"text": "printer is on fire"})
    assert r.status_code == 401


def test_batch_requires_api_key():
    r = client.post("/batch", json={"texts": ["hello"]})
    assert r.status_code == 401


def test_batch_rejects_invalid_api_key():
    r = client.post(
        "/batch",
        json={"texts": ["hello"]},
        headers={"X-API-Key": "not-a-real-key"},
    )
    assert r.status_code == 401


# --- happy path / key_points contract ----------------------------------------


def test_summarize_happy_path_returns_key_points():
    """Regression: LLM uses key_points; response must not KeyError on 'points'."""
    r = client.post("/summarize", json={"text": "printer is on fire"}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "summary" in body
    assert isinstance(body["key_points"], list)
    assert len(body["key_points"]) >= 1
    assert body["sentiment"] in {"positive", "neutral", "negative"}
    assert body["cached"] is False


def test_points_from_accepts_key_points_and_legacy_points():
    assert _points_from({"key_points": ["a"]}) == ["a"]
    assert _points_from({"points": ["b"]}) == ["b"]
    with pytest.raises(KeyError):
        _points_from({"summary": "x"})


def test_to_response_maps_key_points_field():
    resp = _to_response(
        {"summary": "s", "key_points": ["p"], "sentiment": "neutral"},
        cached=False,
    )
    assert resp.key_points == ["p"]
    assert resp.cached is False


# --- cache / force_refresh / style -------------------------------------------


def test_summarize_is_cached_on_second_call():
    payload = {"text": "this exact ticket should be cached the second time"}
    first = client.post("/summarize", json=payload, headers=AUTH)
    second = client.post("/summarize", json=payload, headers=AUTH)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["summary"] == second.json()["summary"]


def test_force_refresh_bypasses_cache():
    text = "force refresh should skip the cache entry"
    first = client.post("/summarize", json={"text": text}, headers=AUTH)
    assert first.status_code == 200
    assert first.json()["cached"] is False

    cached = client.post("/summarize", json={"text": text}, headers=AUTH)
    assert cached.json()["cached"] is True

    refreshed = client.post(
        "/summarize",
        json={"text": text, "force_refresh": True},
        headers=AUTH,
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["cached"] is False


def test_cache_is_keyed_by_style():
    text = "same ticket different styles must not collide"
    brief = client.post(
        "/summarize",
        json={"text": text, "style": "brief"},
        headers=AUTH,
    )
    detailed = client.post(
        "/summarize",
        json={"text": text, "style": "detailed"},
        headers=AUTH,
    )
    assert brief.status_code == 200 and detailed.status_code == 200
    assert brief.json()["cached"] is False
    assert detailed.json()["cached"] is False
    assert brief.json()["summary"] != detailed.json()["summary"]
    assert "Detailed" in detailed.json()["summary"] or "detailed" in detailed.json()[
        "summary"
    ].lower() or "Detailed summary" in detailed.json()["summary"]


# --- markdown-wrapped JSON (mock failure mode) -------------------------------


def test_parse_strips_markdown_json_fence():
    payload = {
        "summary": "ok",
        "key_points": ["one"],
        "sentiment": "neutral",
    }
    raw = f"Sure! Here's the summary:\n```json\n{json.dumps(payload)}\n```"
    assert _parse(raw) == payload


def test_mock_provider_survives_markdown_wrapped_bucket():
    """~1/3 of texts are wrapped in ```json; must still parse (not 502)."""
    text = _text_in_bucket(0)
    assert _stable_bucket(text, 3) == 0
    result = asyncio.run(MockProvider().summarize(text))
    assert "summary" in result
    assert "key_points" in result


def test_summarize_markdown_bucket_text_returns_200():
    text = _text_in_bucket(0, prefix="http-markdown")
    r = client.post("/summarize", json={"text": text}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["key_points"], list)


# --- rate limit --------------------------------------------------------------


def test_rate_limiter_unit_blocks_then_resets_after_window(monkeypatch):
    limiter = RateLimiter(limit=2, window_seconds=10)
    clock = {"t": 1000.0}
    monkeypatch.setattr("app.ratelimit.time.time", lambda: clock["t"])

    assert limiter.allow("k") is True
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False  # over limit

    clock["t"] = 1011.0  # past window
    assert limiter.allow("k") is True  # count reset


def test_summarize_returns_429_when_rate_limited():
    # Use Bob so we don't collide with other tests' Alice quota before fixture reset.
    for i in range(main._limiter.limit):
        r = client.post(
            "/summarize",
            json={"text": f"rate-limit-fill-{i}"},
            headers=AUTH_BOB,
        )
        assert r.status_code == 200, r.text

    blocked = client.post(
        "/summarize",
        json={"text": "rate-limit-should-block"},
        headers=AUTH_BOB,
    )
    assert blocked.status_code == 429
    assert "Rate limit" in blocked.json()["detail"]


# --- retries -----------------------------------------------------------------


def test_call_llm_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def flaky(text, style="brief"):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return {
            "summary": "recovered",
            "key_points": ["ok"],
            "sentiment": "neutral",
        }

    monkeypatch.setattr(main, "_provider", AsyncMock(summarize=flaky))
    monkeypatch.setattr(main.config, "LLM_MAX_RETRIES", 2)

    result = asyncio.run(main._call_llm_with_retries("retry-me"))
    assert result["summary"] == "recovered"
    assert calls["n"] == 3


def test_call_llm_retries_exhausted_raises(monkeypatch):
    async def always_fail(text, style="brief"):
        raise RuntimeError("down")

    monkeypatch.setattr(main, "_provider", AsyncMock(summarize=always_fail))
    monkeypatch.setattr(main.config, "LLM_MAX_RETRIES", 2)

    with pytest.raises(RuntimeError, match="LLM call failed"):
        asyncio.run(main._call_llm_with_retries("never-works"))


def test_summarize_returns_502_when_llm_keeps_failing(monkeypatch):
    async def always_fail(text, style="brief"):
        raise RuntimeError("down")

    monkeypatch.setattr(main, "_provider", AsyncMock(summarize=always_fail))
    monkeypatch.setattr(main.config, "LLM_MAX_RETRIES", 1)

    r = client.post(
        "/summarize",
        json={"text": "will-502"},
        headers=AUTH,
    )
    assert r.status_code == 502


# --- batch -------------------------------------------------------------------


def test_batch_processes_each_item():
    r = client.post(
        "/batch",
        json={"texts": ["order delayed by two days", "refund never arrived"]},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 2
    for i, item in enumerate(body["results"]):
        assert item["index"] == i
        assert item["ok"] is True
        assert item["result"] is not None
        assert "summary" in item["result"]
        assert isinstance(item["result"]["key_points"], list)


def test_batch_isolates_failures():
    """One bad/empty ticket must not fail the whole batch response."""
    r = client.post(
        "/batch",
        json={
            "texts": [
                "package arrived on time thank you",
                "",
                "need help resetting my password please",
            ]
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 3

    assert results[0]["ok"] is True
    assert results[0]["result"] is not None

    assert results[1]["ok"] is False
    assert results[1]["result"] is None
    assert "non-empty" in results[1]["error"]

    assert results[2]["ok"] is True
    assert results[2]["result"] is not None


def test_batch_isolates_llm_item_failure(monkeypatch):
    """One LLM failure in a batch must leave siblings ok."""

    async def selective(text, style="brief"):
        if text == "BAD":
            raise RuntimeError("boom")
        return {
            "summary": f"ok:{text}",
            "key_points": ["p"],
            "sentiment": "neutral",
        }

    monkeypatch.setattr(main, "_provider", AsyncMock(summarize=selective))

    r = client.post(
        "/batch",
        json={"texts": ["GOOD-A", "BAD", "GOOD-B"]},
        headers=AUTH,
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False
    assert "boom" in results[1]["error"]
    assert results[2]["ok"] is True


# --- anthropic helpers -------------------------------------------------------


def test_prompt_format_keeps_braces_in_ticket_text():
    ticket = "Config broken: use {env} and {{double}} braces"
    prompt = _PROMPT.format(version="v1", style="brief", text=ticket)
    assert "{env}" in prompt
    assert "{{double}}" in prompt


def test_text_from_content_collects_text_blocks_only():
    content = [
        SimpleNamespace(type="thinking", text="ignore me"),
        SimpleNamespace(type="text", text='{"summary":"ok"}'),
        {"type": "text", "text": " more"},
    ]
    assert _text_from_content(content) == '{"summary":"ok"}\n more'


def test_text_from_content_rejects_empty_response():
    with pytest.raises(ValueError, match="no text blocks"):
        _text_from_content([SimpleNamespace(type="tool_use", text=None)])
