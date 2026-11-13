"""The xAI API key must never appear in any response or log line."""
import logging

import pytest
from django.urls import reverse

from apps.ai.exceptions import AIServiceUnavailable

from .helpers import text_turn, tool_turn

pytestmark = pytest.mark.django_db


def test_api_key_absent_from_all_responses_and_logs(farmer_client, farmer, farmer_network, fake_grok,
                                                    settings, caplog, api_client):
    caplog.set_level(logging.DEBUG)
    key = settings.XAI_API_KEY
    bodies = []

    fake_grok(tool_turn("find_nearby_farmers"), text_turn("ok"))
    res = farmer_client.post(reverse("ai:chat"), {"message": "near me"}, format="json")
    bodies.append(res.content)
    cid = res.json()["conversation_id"]

    fake_grok(AIServiceUnavailable())
    bodies.append(farmer_client.post(reverse("ai:chat"), {"message": "again"}, format="json").content)

    for url in [reverse("ai:conversations"), reverse("ai:conversation-messages", args=[cid]),
                reverse("accounts:me"), reverse("locations:me"), "/api/v1/health/"]:
        bodies.append(farmer_client.get(url).content)
    bodies.append(api_client.get("/api/schema/").content)
    bodies.append(api_client.get("/api/docs/").content)

    for body in bodies:
        assert key.encode() not in body
    assert key not in caplog.text


def test_settings_secrets_are_redacted_by_log_filter(settings):
    from apps.core.logging import RedactSecretsFilter

    logger = logging.getLogger("apps.test.redact")
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = Capture()
    handler.addFilter(RedactSecretsFilter())
    logger.addHandler(handler)
    try:
        logger.error("calling xAI with key %s", settings.XAI_API_KEY)
        try:
            raise ValueError(f"bad key {settings.XAI_API_KEY}")
        except ValueError:
            logger.exception("failure")
    finally:
        logger.removeHandler(handler)
    joined = "\n".join(records)
    assert settings.XAI_API_KEY not in joined
    assert joined.count("[REDACTED]") >= 2
