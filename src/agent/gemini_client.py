"""Construction of the official Google Gen AI SDK client."""

from __future__ import annotations

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.5-flash-lite"
REQUEST_TIMEOUT_MS = 30_000


class GeminiConfigurationError(RuntimeError):
    """Raised when the runtime has no configured Gemini API key."""


def create_gemini_client(api_key: str | None) -> genai.Client:
    if not isinstance(api_key, str) or not api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured")
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )
