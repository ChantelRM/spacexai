"""Shared pytest fixtures for every app."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import BuyerFactory, FarmerFactory


@pytest.fixture(autouse=True)
def _clear_cache():
    # Throttle counters live in the cache; isolate tests from each other.
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def farmer(db):
    return FarmerFactory()


@pytest.fixture
def buyer(db):
    return BuyerFactory()


@pytest.fixture
def auth_client():
    """auth_client(user) -> APIClient authenticated as that user (no JWT round-trip)."""

    def _make(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _make


@pytest.fixture
def farmer_client(auth_client, farmer):
    return auth_client(farmer)


@pytest.fixture
def buyer_client(auth_client, buyer):
    return auth_client(buyer)
