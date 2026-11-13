import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import Role, User
from apps.ai.tools.registry import execute_tool_call
from apps.locations.models import UserLocation

pytestmark = pytest.mark.django_db


def test_seed_dev_data_is_idempotent_and_feeds_find_nearby_farmers(settings):
    settings.DEBUG = True
    call_command("seed_dev_data", verbosity=0)
    call_command("seed_dev_data", verbosity=0)
    assert User.objects.filter(role=Role.FARMER).count() == 8
    assert User.objects.filter(role=Role.WHOLESALE_BUYER).count() == 5
    assert UserLocation.objects.filter(latitude__isnull=True).exists()
    assert UserLocation.objects.filter(latitude__isnull=False).exists()
    assert UserLocation.objects.values("province").distinct().count() >= 3

    buyer = User.objects.get(email="chef.buyer@example.com")
    result = execute_tool_call(buyer, "find_nearby_farmers", '{"limit": 3}').result
    assert len(result["results"]) == 3
    assert result["results"][0]["location"]["distance"]["basis"] == "gps"

    from apps.bulk.models import BulkPurchase
    from apps.equipment.models import EquipmentListing
    from apps.groups.models import FarmerGroup
    from apps.orders.models import Order
    from apps.transport.models import TransportRequest

    assert set(Order.objects.values_list("status", flat=True)) == {"PENDING", "ACCEPTED", "DISPATCHED", "COMPLETED",
                                                                   "REJECTED"}
    assert FarmerGroup.objects.count() == 2 and BulkPurchase.objects.count() == 1
    assert TransportRequest.objects.count() == 1 and EquipmentListing.objects.count() == 3
    recs = execute_tool_call(buyer, "search_recommended_farmers",
                             '{"produce": "tomatoes", "quantity": 100, "unit": "KG"}').result
    assert recs["count"] >= 2 and recs["results"][0]["match_reasons"]


def test_seed_refuses_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_dev_data", verbosity=0)
