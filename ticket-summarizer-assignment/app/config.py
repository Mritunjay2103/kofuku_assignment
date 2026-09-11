import os


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v1")


VALID_API_KEYS = {
    "demo-key-alice",
    "demo-key-bob",
}


RATE_LIMIT = int(os.getenv("RATE_LIMIT", "5"))
RATE_WINDOW_SECONDS = int(os.getenv("RATE_WINDOW_SECONDS", "60"))


LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
