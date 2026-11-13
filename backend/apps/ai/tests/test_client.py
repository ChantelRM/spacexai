"""Tests for the xAI client wrapper. The SDK client is always replaced by a fake."""
import logging
from types import SimpleNamespace

import httpx2
import openai
import pytest

from apps.ai import client
from apps.ai.exceptions import AIServiceUnavailable

URL = "https://api.x.ai/v1/responses"

# Captured at import, before the autouse fixture blocks it for each test.
REAL_SDK_BUILDER = client._get_sdk_client


def _request():
    return httpx2.Request("POST", URL)


def _status_error(cls, status, message="boom"):
    return cls(message, response=httpx2.Response(status, request=_request()), body=None)


class FakeSDK:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.kwargs = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.kwargs.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _sdk_response():
    return SimpleNamespace(output=[
        SimpleNamespace(type="reasoning", summary=[]),
        SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="Hello farmer")]),
        SimpleNamespace(type="function_call", call_id="call_1", name="find_nearby_farmers",
                        arguments='{"limit": 3}'),
    ])


@pytest.fixture
def sdk(monkeypatch):
    def _install(*outcomes):
        fake = FakeSDK(*outcomes)
        monkeypatch.setattr(client, "_get_sdk_client", lambda *a, **k: fake)
        monkeypatch.setattr(client, "_sleep", lambda s: None)
        return fake

    return _install


def _call(tools=None):
    return client.create_response(instructions="sys", input_items=[client.user_item("hi")],
                                  tools=tools if tools is not None else [{"type": "function", "name": "t"}])


def test_parses_text_and_tool_calls(sdk, settings):
    fake = sdk(_sdk_response())
    turn = _call()
    assert turn.text == "Hello farmer"
    assert turn.tool_calls == [client.ToolCall("call_1", "find_nearby_farmers", '{"limit": 3}')]
    sent = fake.kwargs[0]
    assert sent["model"] == settings.XAI_MODEL
    assert sent["store"] is False
    assert sent["instructions"] == "sys"
    assert sent["tools"] and sent["tool_choice"] == "auto"


def test_no_tools_means_no_tools_param(sdk):
    fake = sdk(_sdk_response())
    _call(tools=[])
    assert "tools" not in fake.kwargs[0]


def test_retries_transient_errors_then_succeeds(sdk, settings):
    settings.XAI_MAX_RETRIES = 2
    fake = sdk(openai.APIConnectionError(request=_request()),
               _status_error(openai.InternalServerError, 502),
               _sdk_response())
    assert _call().text == "Hello farmer"
    assert len(fake.kwargs) == 3


def test_gives_up_after_retries(sdk, settings):
    settings.XAI_MAX_RETRIES = 1
    fake = sdk(openai.APITimeoutError(request=_request()), _status_error(openai.RateLimitError, 429))
    with pytest.raises(AIServiceUnavailable):
        _call()
    assert len(fake.kwargs) == 2


def test_non_transient_errors_are_not_retried(sdk, settings):
    settings.XAI_MAX_RETRIES = 3
    fake = sdk(_status_error(openai.BadRequestError, 400))
    with pytest.raises(AIServiceUnavailable):
        _call()
    assert len(fake.kwargs) == 1


def test_unconfigured_client_is_503(settings):
    settings.XAI_API_KEY = ""
    with pytest.raises(AIServiceUnavailable):
        _call()
    settings.XAI_API_KEY = "x" * 20
    settings.XAI_MODEL = ""
    with pytest.raises(AIServiceUnavailable):
        _call()


def test_api_key_never_logged_or_raised(sdk, settings, caplog):
    """Even if the provider echoes the key in an error message, it must not escape."""
    caplog.set_level(logging.DEBUG)
    settings.XAI_MAX_RETRIES = 1
    leak = f"Incorrect API key provided: {settings.XAI_API_KEY}"
    sdk(_status_error(openai.InternalServerError, 500, leak), _status_error(openai.AuthenticationError, 401, leak))
    with pytest.raises(AIServiceUnavailable) as excinfo:
        _call()
    assert settings.XAI_API_KEY not in caplog.text
    assert settings.XAI_API_KEY not in str(excinfo.value.detail)
    assert excinfo.value.__cause__ is None  # provider exception (with its message) is not chained
    assert "AuthenticationError (HTTP 401)" in caplog.text


def test_real_sdk_client_is_built_with_settings():
    """Build (but never call) a real SDK client to check base URL, timeout and retries."""
    sdk_client = REAL_SDK_BUILDER("xai-test", "https://api.x.ai/v1", 12.0)
    try:
        assert str(sdk_client.base_url).startswith("https://api.x.ai/v1")
        assert sdk_client.max_retries == 0
        assert sdk_client.timeout == 12.0
    finally:
        REAL_SDK_BUILDER.cache_clear()
