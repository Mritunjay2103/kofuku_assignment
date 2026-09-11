# Ticket Summarizer

A Python/FastAPI service for summarizing customer support tickets.

## Setup

Requires Python 3.11 or newer. The service runs in mock mode by default;
no external model credentials are required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API documentation: http://127.0.0.1:8000/docs

Use the `X-API-Key` header with either `demo-key-alice` or `demo-key-bob`.

```bash
curl -s http://127.0.0.1:8000/health

curl -s -X POST http://127.0.0.1:8000/summarize \
  -H 'X-API-Key: demo-key-alice' \
  -H 'Content-Type: application/json' \
  -d '{"text":"My order arrived damaged."}'
```

## Tests

```bash
python -m pytest -q
```

## Task

Review the service, investigate its behavior, and explain any issues you find.
Make focused improvements and add tests that demonstrate their correctness.
Record your findings, reasoning, and any remaining concerns in `FINDINGS.md`.

AI coding tools and documentation are allowed. Be prepared to explain and verify
your changes.
