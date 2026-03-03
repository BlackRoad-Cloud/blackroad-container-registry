"""
Ollama Router
Routes AI chat requests to a local Ollama instance when triggered by
recognised @mention aliases. No external AI providers are used.

Supported aliases (case-insensitive): @copilot, @lucidia,
@blackboxprogramming, @ollama.
"""

from __future__ import annotations

import re
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Alias configuration
# ---------------------------------------------------------------------------

OLLAMA_ALIASES: frozenset[str] = frozenset({
    "copilot",
    "lucidia",
    "blackboxprogramming",
    "ollama",
})

_MENTION_RE = re.compile(r"@([A-Za-z0-9_]+)")

DEFAULT_MODEL = "llama3"
DEFAULT_HOST = "http://localhost:11434"
_ERROR_TEXT_LIMIT = 200

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_mentions(text: str) -> list[str]:
    """Return every @mention token found in *text* (lower-cased, without @)."""
    return [m.lower() for m in _MENTION_RE.findall(text)]


def should_route_to_ollama(text: str) -> bool:
    """Return True if *text* contains at least one recognised Ollama alias."""
    return any(mention in OLLAMA_ALIASES for mention in parse_mentions(text))


def strip_mentions(text: str) -> str:
    """Remove all @mention tokens from *text* and strip surrounding whitespace."""
    return _MENTION_RE.sub("", text).strip()


def route_to_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: int = 120,
) -> dict:
    """
    Send *prompt* to the local Ollama ``/api/generate`` endpoint and return
    the parsed JSON response.

    Raises:
        requests.RequestException: if the HTTP request fails.
        ValueError: if Ollama returns a non-200 status code.
    """
    url = f"{host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    response = requests.post(url, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise ValueError(
            f"Ollama returned HTTP {response.status_code}: {response.text[:_ERROR_TEXT_LIMIT]}"
        )
    return response.json()


def handle_message(
    text: str,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: int = 120,
) -> Optional[dict]:
    """
    High-level entry point.

    If *text* contains a recognised alias, strip the mention(s) and forward
    the remaining prompt to Ollama.  Returns the Ollama JSON response dict,
    or ``None`` if no recognised alias is present.
    """
    if not should_route_to_ollama(text):
        return None
    prompt = strip_mentions(text)
    return route_to_ollama(prompt, model=model, host=host, timeout=timeout)
