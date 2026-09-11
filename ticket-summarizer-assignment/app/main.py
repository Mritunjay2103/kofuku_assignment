import asyncio

from fastapi import Depends, FastAPI, Header, HTTPException

from . import config
from .cache import ResponseCache
from .llm import get_provider
from .models import (
    BatchItemResult,
    BatchRequest,
    BatchResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from .ratelimit import RateLimiter

app = FastAPI(title="Ticket Summarizer", version="0.1.0")

_provider = get_provider()
_cache = ResponseCache()
_limiter = RateLimiter(config.RATE_LIMIT, config.RATE_WINDOW_SECONDS)


def require_api_key(x_api_key: str = Header(default="")) -> str:
    if x_api_key not in config.VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key


def _points_from(data: dict) -> list:
    if "key_points" in data:
        return data["key_points"]
    if "points" in data:
        return data["points"]
    raise KeyError("key_points")


def _to_response(data: dict, *, cached: bool) -> SummarizeResponse:
    return SummarizeResponse(
        summary=data["summary"],
        key_points=_points_from(data),
        sentiment=data["sentiment"],
        cached=cached,
    )


async def _call_llm_with_retries(text: str, style: str = "brief") -> dict:
    last_err: Exception | None = None
    for attempt in range(config.LLM_MAX_RETRIES + 1):
        try:
            return await _provider.summarize(text, style)
        except Exception as exc:
            last_err = exc
            if attempt < config.LLM_MAX_RETRIES:
                await asyncio.sleep(0.05)
    raise RuntimeError(f"LLM call failed: {last_err}")


async def _summarize_one(
    text: str,
    style: str = "brief",
    force_refresh: bool = False,
) -> SummarizeResponse:
    prompt_version = config.PROMPT_VERSION

    if not force_refresh:
        cached = _cache.get(text, style, prompt_version)
        if cached is not None:
            return _to_response(cached, cached=True)

    result = await _call_llm_with_retries(text, style)
    _cache.set(text, style, prompt_version, result)
    return _to_response(result, cached=False)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(
    req: SummarizeRequest,
    api_key: str = Depends(require_api_key),
) -> SummarizeResponse:
    if not _limiter.allow(api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        return await _summarize_one(req.text, req.style, req.force_refresh)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/batch", response_model=BatchResponse)
async def batch(
    req: BatchRequest,
    api_key: str = Depends(require_api_key),
) -> BatchResponse:
    if not _limiter.allow(api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    results: list[BatchItemResult] = []
    for index, text in enumerate(req.texts):
        if not text or not str(text).strip():
            results.append(
                BatchItemResult(index=index, ok=False, error="text must be non-empty")
            )
            continue
        try:
            item = await _summarize_one(text)
            results.append(BatchItemResult(index=index, ok=True, result=item))
        except Exception as exc:
            results.append(BatchItemResult(index=index, ok=False, error=str(exc)))

    return BatchResponse(results=results)
