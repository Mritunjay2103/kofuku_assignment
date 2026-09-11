# Findings (tracker)

Critical functional items **1–8 are fixed** — details in `ticket-summarizer-assignment/FINDINGS.md`.

1. Field name mismatch: key_points vs points — **fixed** (`main.py`)
2. Mock LLM markdown JSON — **fixed** (`llm._parse`)
3. Rate limiter permanent lockout — **fixed** (`ratelimit.py`)
4. force_refresh dead — **fixed** (`_summarize_one`)
5. Cache key ignores style / PROMPT_VERSION — **fixed** (`cache.py`)
6. /batch stub — **fixed** (`main.py`)
7. Anthropic async + text blocks — **fixed** (`llm.py` + requirements)
8. Smoke tests / packaging — **fixed** (expanded suite + `__init__.py` + pytest.ini)

Deferred (config / ops / NFR): 9–18.
