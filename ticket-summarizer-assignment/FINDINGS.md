# Findings

## Critical bugs fixed (1–8)

### 1. `key_points` vs `points` mismatch
**Where:** `app/main.py` (`_points_from`, `_to_response`)  
**Was:** Response builder read `result["points"]` while the LLM returns `key_points` → `KeyError` / 500 on every success.  
**Fix:** Normalize via `_points_from` (prefers `key_points`, accepts legacy `points`).

### 2. Markdown-wrapped mock JSON
**Where:** `app/llm.py` (`_parse`)  
**Was:** Bare `json.loads` failed when the mock wrapped ~1/3 of replies in ` ```json ` fences → deterministic 502.  
**Fix:** Strip fenced blocks before parsing. Same path is used by Anthropic.

### 3. Rate limiter never recovered
**Where:** `app/ratelimit.py`  
**Was:** Window expiry kept the old `count`, so keys stayed blocked forever after one full window.  
**Fix:** On window expiry set `count = 0`, then increment; `reset()` for tests.

### 4. `force_refresh` ignored
**Where:** `app/main.py` (`_summarize_one`)  
**Was:** Field existed on `SummarizeRequest` but was never read.  
**Fix:** When `force_refresh=True`, skip cache read and call the LLM.

### 5. Cache key ignored style / prompt version
**Where:** `app/cache.py`  
**Was:** Keyed only on raw text → brief/detailed collisions; prompt bumps did not invalidate.  
**Fix:** Key is `sha256(f"{prompt_version}:{style}:{text}")`.

### 6. `/batch` stub
**Where:** `app/main.py`  
**Was:** Always 501 despite batch models.  
**Fix:** Process each text with `_summarize_one`; per-item `ok` / `error` so one failure does not fail the batch.

### 7. Anthropic sync client + brittle content access
**Where:** `app/llm.py`, `requirements.txt`  
**Was:** Sync `Anthropic` inside `async def`; assumed `content[0].text`; package missing from deps.  
**Fix:** `AsyncAnthropic` + `await`; `_text_from_content` collects text blocks only; `anthropic>=0.40` in requirements.  
**Note:** Braces in ticket text are safe with `_PROMPT.format(..., text=text)` — values are not re-parsed.

### 8. Tests / packaging
**Where:** `tests/`, `pytest.ini`, `app/__init__.py`, `tests/__init__.py`  
**Was:** Thin smoke tests that assumed a broken happy path; flaky imports.  
**Fix:** Regression coverage for key_points, markdown bucket, rate limit, force_refresh, style cache, retries, batch auth/isolation; `pythonpath = .`; autouse fixture clears cache/limiter.

## Deferred (config / ops / NFR — 9–18)
Not addressed in this pass: dotenv loading, env-based API keys, cache TTL/size, rate-limit-vs-cache ordering policy, retry classification, input max lengths, sentiment enum enforcement, stampede locking, README Windows notes, broader observability.

## How to verify
```bash
python -m pytest -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
