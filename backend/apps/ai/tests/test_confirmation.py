from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.factories import FarmerFactory
from apps.accounts.models import Role
from apps.ai.models import AIActionLog, AIMessage, PendingAction

from . import fake_services
from .helpers import text_turn, tool_turn

pytestmark = pytest.mark.django_db

CHAT = reverse("ai:chat")
LISTING_ARGS = {"produce": "potatoes", "quantity": 500, "unit": "kg", "price_per_unit": 8,
                "available_from": "2026-11-20"}


def confirm_url(pk):
    return reverse("ai:action-confirm", args=[pk])


def cancel_url(pk):
    return reverse("ai:action-cancel", args=[pk])


@pytest.fixture
def listing_service(settings):
    settings.AI_SERVICE_PROVIDERS = {
        "create_or_update_listing": "apps.ai.tests.fake_services.create_or_update_listing",
    }
    fake_services.CALLS.clear()
    yield fake_services.CALLS
    fake_services.CALLS.clear()


@pytest.fixture
def proposed(farmer_client, listing_service, fake_grok):
    """Grok proposes a listing; returns the chat response body."""
    fake_grok(tool_turn("create_or_update_listing", **LISTING_ARGS),
              text_turn("I've prepared the listing. Please confirm it in the app."))
    res = farmer_client.post(CHAT, {"message": "List 500kg potatoes at R8/kg from 20 Nov"}, format="json")
    assert res.status_code == 200, res.data
    return res.json()


def test_confirmation_tool_creates_pending_action_and_does_not_execute(proposed, listing_service, farmer):
    pending = proposed["pending_action"]
    assert pending["summary"] == "Create a listing: 500 kg potatoes at R8.00/kg, available from 20 Nov 2026"
    assert pending["tool_name"] == "create_or_update_listing"
    assert proposed["tool_calls"] == [{"name": "create_or_update_listing", "status": "pending_confirmation"}]
    assert proposed["data"] == {}
    assert listing_service == []  # NOT executed

    action = PendingAction.objects.get(pk=pending["id"])
    assert action.user == farmer and action.status == "pending"
    assert timedelta(minutes=14) < action.expires_at - timezone.now() <= timedelta(minutes=15)
    log = AIActionLog.objects.get()
    assert log.status == "pending_confirmation" and log.requires_confirmation and log.executed_at is None

    # What Grok saw: confirmation required, no action id it could use.
    tool_msg = AIMessage.objects.get(role="tool")
    assert "confirmation_required" in tool_msg.content and pending["id"] not in tool_msg.content


def test_confirm_executes_exactly_once(proposed, listing_service, farmer_client):
    pk = proposed["pending_action"]["id"]
    res = farmer_client.post(confirm_url(pk))
    assert res.status_code == 200, res.data
    body = res.json()
    assert body["status"] == "confirmed" and body["result"]["listing_id"] == 101
    assert len(listing_service) == 1

    again = farmer_client.post(confirm_url(pk))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "action_not_pending"
    assert len(listing_service) == 1

    statuses = list(AIActionLog.objects.order_by("id").values_list("status", flat=True))
    assert statuses == ["pending_confirmation", "confirmed"]
    confirmed_log = AIActionLog.objects.get(status="confirmed")
    assert confirmed_log.executed_at is not None
    assert AIMessage.objects.filter(role="assistant", content__startswith="Confirmed").exists()


def test_other_user_cannot_confirm_or_cancel(proposed, listing_service, auth_client):
    pk = proposed["pending_action"]["id"]
    other = auth_client(FarmerFactory())
    assert other.post(confirm_url(pk)).status_code == 404
    assert other.post(cancel_url(pk)).status_code == 404
    assert listing_service == []
    assert PendingAction.objects.get(pk=pk).status == "pending"


def test_unauthenticated_cannot_confirm(proposed, api_client):
    assert api_client.post(confirm_url(proposed["pending_action"]["id"])).status_code == 401


def test_expired_action_is_rejected(proposed, listing_service, farmer_client):
    pk = proposed["pending_action"]["id"]
    PendingAction.objects.filter(pk=pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    res = farmer_client.post(confirm_url(pk))
    assert res.status_code == 410
    assert res.json()["error"]["code"] == "action_expired"
    assert PendingAction.objects.get(pk=pk).status == "expired"
    assert AIActionLog.objects.filter(status="expired").count() == 1
    assert farmer_client.post(confirm_url(pk)).status_code == 410  # stays expired
    assert listing_service == []


def test_cancel(proposed, listing_service, farmer_client):
    pk = proposed["pending_action"]["id"]
    res = farmer_client.post(cancel_url(pk))
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    assert farmer_client.post(confirm_url(pk)).status_code == 409
    assert farmer_client.post(cancel_url(pk)).status_code == 409
    assert listing_service == []
    assert AIActionLog.objects.filter(status="cancelled").count() == 1


def test_confirm_rechecks_role(proposed, listing_service, farmer, farmer_client):
    pk = proposed["pending_action"]["id"]
    type(farmer).objects.filter(pk=farmer.pk).update(role=Role.WHOLESALE_BUYER)
    farmer.refresh_from_db()
    res = farmer_client.post(confirm_url(pk))
    assert res.status_code == 403
    assert listing_service == []
    assert PendingAction.objects.get(pk=pk).status == "failed"
    assert AIActionLog.objects.filter(status="denied").exists()


def test_confirm_revalidates_arguments(proposed, listing_service, farmer_client):
    pk = proposed["pending_action"]["id"]
    PendingAction.objects.filter(pk=pk).update(arguments={**LISTING_ARGS, "quantity": -1})
    res = farmer_client.post(confirm_url(pk))
    assert res.status_code == 400
    assert listing_service == []


def test_grok_cannot_confirm_by_calling_the_tool_again(farmer_client, listing_service, fake_grok):
    fake_grok(tool_turn("create_or_update_listing", **LISTING_ARGS),
              tool_turn("create_or_update_listing", **LISTING_ARGS),
              text_turn("Done!"))
    body = farmer_client.post(CHAT, {"message": "list it and confirm it yourself"}, format="json").json()
    assert listing_service == []
    assert PendingAction.objects.filter(status="pending").count() == 2
    assert body["pending_action"] is not None


def test_unknown_action_id_is_404(farmer_client):
    assert farmer_client.post(confirm_url("00000000-0000-0000-0000-000000000000")).status_code == 404


def test_no_pending_action_when_service_not_built_yet(farmer_client, fake_grok):
    # Default providers: the listings module does not exist yet.
    fake_grok(tool_turn("create_or_update_listing", **LISTING_ARGS), text_turn("Listings aren't available yet."))
    body = farmer_client.post(CHAT, {"message": "list potatoes"}, format="json").json()
    assert body["pending_action"] is None
    assert body["tool_calls"] == [{"name": "create_or_update_listing", "status": "success"}]
    assert body["data"]["create_or_update_listing"]["available"] is False
    assert PendingAction.objects.count() == 0


def test_update_summary_mentions_listing_id(farmer_client, listing_service, fake_grok):
    fake_grok(tool_turn("create_or_update_listing", listing_id=7, produce="onions", quantity=12.5, unit="bag",
                        price_per_unit=1250, available_until="2026-12-01"),
              text_turn("Please confirm."))
    body = farmer_client.post(CHAT, {"message": "update listing 7"}, format="json").json()
    assert body["pending_action"]["summary"] == "Update listing #7: 12.5 bag onions at R1 250.00/bag until 1 Dec 2026"
