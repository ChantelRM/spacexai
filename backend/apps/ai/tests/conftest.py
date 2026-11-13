from decimal import Decimal

import pytest

from apps.accounts.factories import FarmerFactory
from apps.ai.tools import registry
from apps.locations.factories import UserLocationFactory
from apps.locations.models import Province

from .helpers import FakeGrok


@pytest.fixture
def fake_grok(monkeypatch):
    """fake_grok(*turns, repeat_last=False) -> FakeGrok installed as the Grok client."""

    def _install(*turns, repeat_last=False):
        fake = FakeGrok(*turns, repeat_last=repeat_last)
        monkeypatch.setattr("apps.ai.client.create_response", fake)
        return fake

    return _install


@pytest.fixture
def restore_registry():
    """Lets a test register temporary tools without leaking them to other tests."""
    snapshot = dict(registry.REGISTRY)
    yield registry
    registry.REGISTRY.clear()
    registry.REGISTRY.update(snapshot)


# Johannesburg CBD and nearby places, with real coordinates.
JHB = (Decimal("-26.204100"), Decimal("28.047300"))
SOWETO = (Decimal("-26.267800"), Decimal("27.858500"))
PTA = (Decimal("-25.747900"), Decimal("28.229300"))


@pytest.fixture
def farmer_network(db, farmer):
    """
    ``farmer`` (the requester) in Johannesburg with GPS, and other farmers:
    Soweto (GPS), Pretoria (GPS), Johannesburg (no GPS), Polokwane (no GPS).
    """
    UserLocationFactory(user=farmer, latitude=JHB[0], longitude=JHB[1], address_line="1 Private Rd")
    others = {
        "soweto": UserLocationFactory(user=FarmerFactory(display_name="Soweto Greens"), town="Soweto",
                                      latitude=SOWETO[0], longitude=SOWETO[1], address_line="9 Hidden Lane"),
        "pretoria": UserLocationFactory(user=FarmerFactory(display_name="Tshwane Farm"),
                                        municipality="City of Tshwane", town="Pretoria",
                                        latitude=PTA[0], longitude=PTA[1]),
        "jhb_no_gps": UserLocationFactory(user=FarmerFactory(display_name="Jozi Veg")),
        "limpopo": UserLocationFactory(user=FarmerFactory(display_name="Limpopo Roots"),
                                       province=Province.LIMPOPO, municipality="Polokwane", town="Polokwane"),
    }
    return others
