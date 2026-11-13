"""
Thin wrapper around the ``openai`` SDK pointed at xAI's OpenAI-compatible API.

Uses the **Responses API** (xAI's recommended endpoint for tool calling; Chat
Completions is marked legacy in their docs). We run it statelessly
(``store=False``) and re-send the conversation each round, so nothing about
our users is kept on xAI's side beyond the request itself.

Everything else in the app calls exactly one function, ``create_response``,
and gets back a provider-neutral ``ModelTurn``. Tests patch that one function:

    with patch("apps.ai.client.create_response", side_effect=[...]): ...

The API key is read from settings and is never logged, returned or put in an
error message.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from functools import lru_cache

from django.conf import settings

from .exceptions import AIServiceUnavailable

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: str  # JSON string exactly as the model produced it


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


# --- Input item builders (Responses API format) -------------------------------

def user_item(text: str) -> dict:
    return {"role": "user", "content": text}


def assistant_item(text: str) -> dict:
    return {"role": "assistant", "content": text}


def function_call_item(call: ToolCall) -> dict:
    return {"type": "function_call", "call_id": call.call_id, "name": call.name, "arguments": call.arguments}


def function_output_item(call_id: str, output: str) -> dict:
    return {"type": "function_call_output", "call_id": call_id, "output": output}


# --- Client ----------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_sdk_client(api_key: str, base_url: str, timeout: float):
    from openai import OpenAI

    # Retries are handled below so we control backoff and logging.
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


def _is_transient(exc: Exception) -> bool:
    import openai

    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError,
                        openai.InternalServerError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code in (408, 409, 429) or exc.status_code >= 500
    return False


def _describe(exc: Exception) -> str:
    """Safe one-line description for logs: class and HTTP status only, never the message body."""
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


def _sleep(seconds: float) -> None:  # separate function so tests can patch it
    time.sleep(seconds)


def _parse(response) -> ModelTurn:
    turn = ModelTurn()
    texts = []
    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None)
        if item_type == "function_call":
            turn.tool_calls.append(ToolCall(call_id=item.call_id, name=item.name, arguments=item.arguments or "{}"))
        elif item_type == "message":
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) in ("output_text", "text") and getattr(part, "text", None):
                    texts.append(part.text)
    turn.text = "\n".join(texts).strip()
    return turn


def create_response(*, instructions: str, input_items: list[dict], tools: list[dict]) -> ModelTurn:
    """
    Call Grok once. Retries transient failures with exponential backoff.
    Raises ``AIServiceUnavailable`` (HTTP 503) on any failure.
    """
    if not settings.XAI_API_KEY or not settings.XAI_MODEL:
        logger.error("AI request refused: XAI_API_KEY or XAI_MODEL is not configured")
        raise AIServiceUnavailable()

    client = _get_sdk_client(settings.XAI_API_KEY, settings.XAI_BASE_URL, float(settings.XAI_TIMEOUT_SECONDS))
    kwargs = {
        "model": settings.XAI_MODEL,
        "instructions": instructions,
        "input": input_items,
        "store": False,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    attempts = 1 + max(0, int(settings.XAI_MAX_RETRIES))
    for attempt in range(1, attempts + 1):
        try:
            response = client.responses.create(**kwargs)
            return _parse(response)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a 503
            transient = _is_transient(exc)
            if transient and attempt < attempts:
                delay = min(8.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.25)
                logger.warning("Grok call failed (%s), retry %d/%d in %.1fs",
                               _describe(exc), attempt, attempts - 1, delay)
                _sleep(delay)
                continue
            logger.error("Grok call failed (%s) after %d attempt(s)", _describe(exc), attempt)
            raise AIServiceUnavailable() from None
    raise AIServiceUnavailable()  # pragma: no cover
