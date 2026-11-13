import json

import pytest
from django.urls import reverse
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.factories import FarmerFactory
from apps.ai.exceptions import AIServiceUnavailable
from apps.ai.models import AIActionLog, AIConversation, AIMessage

from .helpers import coordinate_fragments, text_turn, tool_turn

pytestmark = pytest.mark.django_db

CHAT = reverse("ai:chat")
CONVERSATIONS = reverse("ai:conversations")


def messages_url(conversation_id):
    return reverse("ai:conversation-messages", args=[conversation_id])


def test_tool_call_round_trip(farmer_client, farmer, farmer_network, fake_grok):
    grok = fake_grok(
        tool_turn("find_nearby_farmers", limit=2),
        text_turn("The nearest farmers are Jozi Veg and Soweto Greens."),
    )
    res = farmer_client.post(CHAT, {"message": "Find farmers near me"}, format="json")
    assert res.status_code == 200, res.data
    body = res.json()
    assert body["reply"] == "The nearest farmers are Jozi Veg and Soweto Greens."
    assert body["tool_calls"] == [{"name": "find_nearby_farmers", "status": "success"}]
    assert [r["display_name"] for r in body["data"]["find_nearby_farmers"]["results"]] == ["Jozi Veg", "Soweto Greens"]
    assert body["pending_action"] is None

    # The tool result was fed back to Grok on the second call.
    second_input = grok.calls[1]["input_items"]
    assert second_input[-2]["type"] == "function_call"
    assert second_input[-1]["type"] == "function_call_output"
    assert "Jozi Veg" in second_input[-1]["output"]

    conversation = AIConversation.objects.get(pk=body["conversation_id"])
    assert conversation.user == farmer and conversation.title == "Find farmers near me"
    assert list(conversation.messages.values_list("role", flat=True)) == ["user", "tool", "assistant"]
    tool_msg = conversation.messages.get(role="tool")
    assert tool_msg.tool_name == "find_nearby_farmers" and tool_msg.tool_call_id
    assert AIActionLog.objects.get().status == "success"


def test_only_role_tools_are_sent(buyer_client, farmer_client, fake_grok):
    grok = fake_grok(text_turn("Hi"))
    buyer_client.post(CHAT, {"message": "hello"}, format="json")
    assert grok.tool_names() == ["compare_listings", "create_order", "find_nearby_farmers", "get_my_orders",
                                 "search_recommended_farmers"]

    grok = fake_grok(text_turn("Hi"))
    farmer_client.post(CHAT, {"message": "hello"}, format="json")
    assert "search_recommended_farmers" not in grok.tool_names()
    assert "create_or_update_listing" in grok.tool_names()


def test_buyer_cannot_run_farmer_tool_even_if_grok_asks(buyer_client, fake_grok):
    fake_grok(tool_turn("find_equipment", equipment_type="tractor"), text_turn("Sorry, I can't do that."))
    body = buyer_client.post(CHAT, {"message": "find me a tractor"}, format="json").json()
    assert body["tool_calls"] == [{"name": "find_equipment", "status": "denied"}]
    assert body["data"] == {}
    assert AIActionLog.objects.get().status == "denied"


def test_system_prompt_has_context_but_no_coordinates(farmer_client, farmer, farmer_network, fake_grok):
    grok = fake_grok(text_turn("Hi"))
    farmer_client.post(CHAT, {"message": "hello"}, format="json")
    prompt = grok.calls[0]["instructions"]
    loc = farmer.location
    assert farmer.display_name in prompt and "Farmer" in prompt
    assert loc.town in prompt and loc.municipality in prompt and "Gauteng" in prompt
    assert str(loc.latitude) not in prompt and str(loc.longitude) not in prompt and "Private Rd" not in prompt
    assert "Never invent" in prompt and "insur" in prompt


def test_max_tool_rounds(farmer_client, farmer, settings, fake_grok):
    grok = fake_grok(tool_turn("find_nearby_farmers"), repeat_last=True)
    body = farmer_client.post(CHAT, {"message": "loop forever"}, format="json").json()
    assert len(body["tool_calls"]) == settings.AI_MAX_TOOL_ROUNDS == 5
    assert AIActionLog.objects.count() == 5
    assert len(grok.calls) == 6
    assert all(call["tools"] for call in grok.calls[:5])
    assert grok.calls[5]["tools"] == []  # final call: no tools, must answer
    assert body["reply"]  # fallback text when Grok gives none


def test_grok_outage_returns_503(farmer_client, fake_grok, settings):
    fake_grok(AIServiceUnavailable())
    res = farmer_client.post(CHAT, {"message": "hello"}, format="json")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "ai_service_unavailable"
    assert settings.XAI_API_KEY not in res.content.decode()


def test_conversation_continues_with_history(farmer_client, fake_grok):
    fake_grok(text_turn("First answer"))
    cid = farmer_client.post(CHAT, {"message": "first question"}, format="json").json()["conversation_id"]
    grok = fake_grok(text_turn("Second answer"))
    res = farmer_client.post(CHAT, {"conversation_id": cid, "message": "second question"}, format="json")
    assert res.json()["conversation_id"] == cid
    items = grok.calls[0]["input_items"]
    assert items == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "second question"},
    ]


def test_cannot_use_someone_elses_conversation(farmer_client, auth_client, fake_grok):
    fake_grok(text_turn("ok"))
    cid = farmer_client.post(CHAT, {"message": "mine"}, format="json").json()["conversation_id"]
    other = auth_client(FarmerFactory())
    fake_grok(text_turn("ok"))
    res = other.post(CHAT, {"conversation_id": cid, "message": "hijack"}, format="json")
    assert res.status_code == 404
    assert other.get(messages_url(cid)).status_code == 404
    assert AIMessage.objects.filter(content="hijack").count() == 0


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}, {"message": "x" * 2001},
                                     {"message": "hi", "conversation_id": "not-a-uuid"}])
def test_chat_validation(farmer_client, payload, fake_grok):
    grok = fake_grok()
    res = farmer_client.post(CHAT, payload, format="json")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "validation_error"
    assert grok.calls == []


def test_chat_requires_auth(api_client):
    assert api_client.post(CHAT, {"message": "hi"}, format="json").status_code == 401


def test_chat_is_throttled(farmer_client, fake_grok, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"ai_chat": "2/min"})
    fake_grok(text_turn("a"), text_turn("b"), text_turn("c"))
    assert farmer_client.post(CHAT, {"message": "1"}, format="json").status_code == 200
    assert farmer_client.post(CHAT, {"message": "2"}, format="json").status_code == 200
    res = farmer_client.post(CHAT, {"message": "3"}, format="json")
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "throttled"


def test_conversation_list_and_messages_owner_only(farmer_client, buyer_client, fake_grok):
    fake_grok(text_turn("a1"), text_turn("b1"))
    cid = farmer_client.post(CHAT, {"message": "farmer q"}, format="json").json()["conversation_id"]
    buyer_client.post(CHAT, {"message": "buyer q"}, format="json")

    res = farmer_client.get(CONVERSATIONS)
    assert res.status_code == 200
    assert [c["title"] for c in res.json()["results"]] == ["farmer q"]
    assert res.json()["count"] == 1

    res = farmer_client.get(messages_url(cid))
    assert [(m["role"], m["content"]) for m in res.json()["results"]] == [("user", "farmer q"), ("assistant", "a1")]
    assert buyer_client.get(messages_url(cid)).status_code == 404


def test_other_farmers_coordinates_never_reach_any_response(farmer_client, farmer, farmer_network, fake_grok):
    fake_grok(tool_turn("find_nearby_farmers"), text_turn("Here they are."))
    body = farmer_client.post(CHAT, {"message": "near me"}, format="json").content.decode()
    cid = json.loads(body)["conversation_id"]
    history = farmer_client.get(messages_url(cid)).content.decode()
    for loc in farmer_network.values():
        for text in (body, history):
            for fragment in coordinate_fragments(loc):
                assert fragment not in text
            assert loc.user.email not in text
            assert "Hidden Lane" not in text
