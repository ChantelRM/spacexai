import json

import pytest
from rest_framework import serializers

from apps.accounts.factories import BuyerFactory
from apps.accounts.models import Role
from apps.ai.models import AIActionLog, PendingAction
from apps.ai.services_contract import NOT_AVAILABLE, SERVICE_PROVIDERS
from apps.ai.tools import registry
from apps.ai.tools.privacy import scrub_private_fields
from apps.ai.tests.helpers import coordinate_fragments
from apps.ai.tools.registry import (
    execute_tool_call,
    grok_tools_for_user,
    register_tool,
    resolve_service,
    tools_for_user,
)

pytestmark = pytest.mark.django_db

ALL_TOOLS = {
    "find_nearby_farmers", "search_recommended_farmers", "search_buyer_requirements",
    "create_or_update_listing", "find_bulk_purchases", "calculate_cost_shares",
    "find_transport_requests", "find_farmer_groups", "find_equipment",
    "compare_listings", "create_order", "get_my_orders", "respond_to_order",
    "join_bulk_purchase", "confirm_bulk_purchase_contribution", "join_transport_request",
    "request_equipment_booking",
}
BUYER_TOOLS = {"find_nearby_farmers", "search_recommended_farmers", "compare_listings", "create_order",
               "get_my_orders"}
FARMER_TOOLS = ALL_TOOLS - {"search_recommended_farmers", "compare_listings", "create_order"}
CONFIRMATION_TOOLS = {"create_or_update_listing", "create_order", "respond_to_order", "join_bulk_purchase",
                      "confirm_bulk_purchase_contribution", "join_transport_request", "request_equipment_booking"}


def test_all_tools_registered_with_valid_schemas():
    assert set(registry.REGISTRY) == ALL_TOOLS
    for spec in registry.REGISTRY.values():
        tool = spec.as_grok_tool()
        assert tool["type"] == "function" and tool["name"] == spec.name and tool["description"]
        params = tool["parameters"]
        assert params["type"] == "object" and params["additionalProperties"] is False
        json.dumps(tool)  # serialisable
        assert spec.service in SERVICE_PROVIDERS
    assert registry.REGISTRY["create_or_update_listing"].requires_confirmation
    assert {n for n, s in registry.REGISTRY.items() if s.requires_confirmation} == CONFIRMATION_TOOLS


def test_role_filtering(farmer, buyer):
    assert {s.name for s in tools_for_user(farmer)} == FARMER_TOOLS
    assert {s.name for s in tools_for_user(buyer)} == BUYER_TOOLS
    assert {t["name"] for t in grok_tools_for_user(buyer)} == BUYER_TOOLS


def test_inactive_or_anonymous_users_get_no_tools(farmer):
    from django.contrib.auth.models import AnonymousUser

    assert tools_for_user(AnonymousUser()) == []
    farmer.is_active = False
    assert tools_for_user(farmer) == []


def test_no_tool_can_confirm_pending_actions():
    """Commitment tools are themselves gated; nothing in the registry can confirm or cancel a PendingAction."""
    import inspect

    for name, spec in registry.REGISTRY.items():
        if "confirm" in name or "join" in name or "order" in name and name != "get_my_orders":
            assert spec.requires_confirmation, name
        source = inspect.getsource(spec.func)
        assert "PendingAction" not in source and "confirm_pending_action" not in source


def test_denied_call_is_logged(buyer):
    outcome = execute_tool_call(buyer, "search_buyer_requirements", "{}")
    assert outcome.status == "denied"
    assert outcome.result["error"] == "permission_denied"
    log = AIActionLog.objects.get()
    assert (log.status, log.tool_name, log.user) == ("denied", "search_buyer_requirements", buyer)


@pytest.mark.parametrize(
    "arguments,field",
    [
        (json.dumps({"max_distance_km": -5}), "max_distance_km"),
        (json.dumps({"limit": 500}), "limit"),
        (json.dumps({"unexpected": 1, "max_distance_km": "far"}), "max_distance_km"),
        ("not json", "non_field_errors"),
        ("[1, 2]", "non_field_errors"),
    ],
)
def test_invalid_arguments_are_rejected_and_logged(farmer, arguments, field):
    outcome = execute_tool_call(farmer, "find_nearby_farmers", arguments)
    assert outcome.status == "invalid"
    assert outcome.result["error"] == "invalid_arguments"
    assert field in outcome.result["details"]
    assert AIActionLog.objects.get().status == "invalid"


def test_invalid_listing_arguments(farmer):
    outcome = execute_tool_call(farmer, "create_or_update_listing", json.dumps(
        {"produce": "potatoes", "quantity": 0, "unit": "SACKS", "price_per_unit": 8}))
    assert outcome.status == "invalid"
    assert {"quantity", "unit"} <= set(outcome.result["details"])
    assert PendingAction.objects.count() == 0


def test_unknown_tool_is_logged(farmer):
    outcome = execute_tool_call(farmer, "drop_tables", "{}")
    assert outcome.status == "invalid"
    assert AIActionLog.objects.get().tool_name == "drop_tables"


def test_success_is_logged(farmer, farmer_network):
    outcome = execute_tool_call(farmer, "find_nearby_farmers", json.dumps({"limit": 3}))
    assert outcome.status == "success"
    assert outcome.data == outcome.result
    log = AIActionLog.objects.get()
    assert log.status == "success" and log.executed_at is not None
    assert log.arguments == {"limit": 3}
    assert log.result_summary == "3 result(s)"


def test_find_nearby_farmers_orders_and_hides_private_data(farmer, farmer_network):
    result = execute_tool_call(farmer, "find_nearby_farmers", "{}").result
    names = [r["display_name"] for r in result["results"]]
    assert names == ["Jozi Veg", "Soweto Greens", "Tshwane Farm", "Limpopo Roots"]
    assert result["results"][1]["location"]["distance"]["basis"] == "gps"
    assert result["results"][0]["location"]["distance"]["basis"] == "same_town"
    assert farmer.display_name not in names  # never returns yourself

    blob = json.dumps(result) + json.dumps(list(AIActionLog.objects.values("arguments", "result_summary")))
    for loc in farmer_network.values():
        for fragment in coordinate_fragments(loc):
            assert fragment not in blob
        assert loc.user.email not in blob
        assert loc.user.phone_number not in blob
    assert "Hidden Lane" not in blob and "latitude" not in blob and "longitude" not in blob


def test_find_nearby_farmers_max_distance(farmer, farmer_network):
    result = execute_tool_call(farmer, "find_nearby_farmers", json.dumps({"max_distance_km": 30})).result
    assert [r["display_name"] for r in result["results"]] == ["Jozi Veg", "Soweto Greens"]


def test_find_nearby_farmers_excludes_buyers_and_handles_missing_location(farmer, farmer_network):
    from apps.locations.factories import UserLocationFactory

    UserLocationFactory(user=BuyerFactory(display_name="Big Buyer"))
    names = [r["display_name"] for r in execute_tool_call(farmer, "find_nearby_farmers", "{}").result["results"]]
    assert "Big Buyer" not in names

    no_location_buyer = BuyerFactory()
    result = execute_tool_call(no_location_buyer, "find_nearby_farmers", "{}").result
    assert result["results"] == [] and "location" in result["message"]


def test_every_tool_has_a_real_service():
    for spec in registry.REGISTRY.values():
        assert resolve_service(spec.service) is not None, spec.name


@pytest.mark.parametrize("name,args", [
    ("find_bulk_purchases", {"item": "fertiliser"}),
    ("calculate_cost_shares", {"total_cost": 1200, "split_method": "equal",
                               "participants": [{"label": "A"}, {"label": "B"}]}),
    ("find_transport_requests", {"destination_town": "Johannesburg"}),
    ("find_farmer_groups", {"focus": "security"}),
    ("find_equipment", {"equipment_type": "tractor"}),
])
def test_coop_search_tools_run(farmer, name, args):
    outcome = execute_tool_call(farmer, name, json.dumps(args))
    assert outcome.status == "success", outcome.result
    assert outcome.result["available"] is True


def test_missing_service_reports_not_available(farmer, settings):
    settings.AI_SERVICE_PROVIDERS = {"find_equipment": "apps.not_built.services.find_equipment"}
    outcome = execute_tool_call(farmer, "find_equipment", "{}")
    assert outcome.result == NOT_AVAILABLE
    assert AIActionLog.objects.get().result_summary == "Feature not available yet"


def test_recommendation_tools_are_real_services(buyer, farmer):
    outcome = execute_tool_call(buyer, "search_recommended_farmers",
                                json.dumps({"produce": "potatoes", "quantity": 500, "unit": "KG"}))
    assert outcome.result["available"] is True and outcome.result["results"] == []
    outcome = execute_tool_call(farmer, "search_buyer_requirements", json.dumps({"produce": "tomatoes"}))
    assert outcome.result["available"] is True and outcome.result["count"] == 0


def test_cost_share_by_quantity_requires_quantities(farmer):
    outcome = execute_tool_call(farmer, "calculate_cost_shares", json.dumps(
        {"total_cost": 100, "split_method": "by_quantity", "participants": [{"label": "A"}, {"label": "B", "quantity": 2}]}))
    assert outcome.status == "invalid"


class _EchoInput(serializers.Serializer):
    pass


def test_results_are_scrubbed_and_errors_are_logged(farmer, restore_registry):
    @register_tool(name="leaky", description="x", input_serializer=_EchoInput, allowed_roles={Role.FARMER})
    def leaky(user, data):
        return {"results": [{"display_name": "A", "email": "a@x.com", "phone_number": "1",
                             "location": {"town": "T", "latitude": 1.5, "longitude": 2.5}}]}

    @register_tool(name="broken", description="x", input_serializer=_EchoInput, allowed_roles={Role.FARMER})
    def broken(user, data):
        raise RuntimeError("database exploded with secret details")

    result = execute_tool_call(farmer, "leaky", "{}").result
    assert result == {"results": [{"display_name": "A", "location": {"town": "T"}}]}

    outcome = execute_tool_call(farmer, "broken", "{}")
    assert outcome.status == "error"
    assert "secret details" not in json.dumps(outcome.result)
    assert AIActionLog.objects.filter(status="error", tool_name="broken").exists()


def test_tool_runs_as_requesting_user(farmer, restore_registry):
    seen = {}

    @register_tool(name="whoami", description="x", input_serializer=_EchoInput, allowed_roles={Role.FARMER})
    def whoami(user, data):
        seen["user"] = user
        return {}

    execute_tool_call(farmer, "whoami", "{}")
    assert seen["user"] == farmer and not seen["user"].is_superuser


def test_register_tool_validation(restore_registry):
    with pytest.raises(ValueError):
        register_tool(name="find_nearby_farmers", description="dup", input_serializer=_EchoInput,
                      allowed_roles={Role.FARMER})(lambda u, d: {})
    with pytest.raises(ValueError):
        register_tool(name="x", description="x", input_serializer=_EchoInput, allowed_roles={"ADMIN"})
    with pytest.raises(ValueError):
        register_tool(name="y", description="y", input_serializer=_EchoInput, allowed_roles={Role.FARMER},
                      requires_confirmation=True)


def test_resolve_service(settings):
    assert resolve_service("find_nearby_farmers") is not None
    settings.AI_SERVICE_PROVIDERS = {"find_equipment": "apps.not_built.services.find_equipment"}
    assert resolve_service("find_equipment") is None  # module not written yet
    settings.AI_SERVICE_PROVIDERS = {"find_equipment": "apps.ai.tests.broken_service_module.find_equipment"}
    with pytest.raises(ModuleNotFoundError):  # a real bug inside an existing module must surface
        resolve_service("find_equipment")


def test_scrub_private_fields_nested():
    data = {"a": [{"Email": "x", "b": {"lat": 1, "lng": 2, "keep": 3}}], "phone": "1"}
    assert scrub_private_fields(data) == {"a": [{"b": {"keep": 3}}]}
