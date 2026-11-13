import logging

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.test import APIRequestFactory

from apps.accounts.factories import BuyerFactory, FarmerFactory
from apps.accounts.models import Role
from apps.core.exceptions import api_exception_handler
from apps.core.logging import RedactSecretsFilter
from apps.core.pagination import StandardPagination
from apps.core.permissions import (
    IsFarmer,
    IsOwner,
    IsOwnerOrReadOnly,
    IsWholesaleBuyer,
    role_required,
)

pytestmark = pytest.mark.django_db
rf = APIRequestFactory()


def _request(user, method="get"):
    request = getattr(rf, method)("/")
    request.user = user
    return request


class _Obj:
    def __init__(self, user):
        self.user = user


class _View:
    owner_field = "user"


# --- Permissions -------------------------------------------------------------

def test_role_permissions():
    farmer, buyer = FarmerFactory(), BuyerFactory()
    from django.contrib.auth.models import AnonymousUser

    anon = AnonymousUser()
    assert IsFarmer().has_permission(_request(farmer), None)
    assert not IsFarmer().has_permission(_request(buyer), None)
    assert not IsFarmer().has_permission(_request(anon), None)
    assert IsWholesaleBuyer().has_permission(_request(buyer), None)
    assert not IsWholesaleBuyer().has_permission(_request(farmer), None)
    assert not IsWholesaleBuyer().has_permission(_request(anon), None)


def test_role_required():
    farmer, buyer = FarmerFactory(), BuyerFactory()
    both = role_required(Role.FARMER, Role.WHOLESALE_BUYER)()
    only_buyer = role_required(Role.WHOLESALE_BUYER)()
    assert both.has_permission(_request(farmer), None)
    assert both.has_permission(_request(buyer), None)
    assert not only_buyer.has_permission(_request(farmer), None)
    with pytest.raises(ValueError):
        role_required("SUPPLIER")


def test_owner_permissions():
    owner, other = FarmerFactory(), FarmerFactory()
    obj = _Obj(owner)
    perm = IsOwnerOrReadOnly()
    assert perm.has_object_permission(_request(other, "get"), _View(), obj)
    assert not perm.has_object_permission(_request(other, "patch"), _View(), obj)
    assert perm.has_object_permission(_request(owner, "patch"), _View(), obj)
    assert not IsOwner().has_object_permission(_request(other, "get"), _View(), obj)
    assert IsOwner().has_object_permission(_request(owner, "get"), _View(), obj)
    # A User object is owned only by itself.
    assert IsOwner().has_object_permission(_request(owner), _View(), owner)
    assert not IsOwner().has_object_permission(_request(other), _View(), owner)


def test_unauthenticated_request_uses_error_format(api_client):
    res = api_client.get("/api/v1/auth/me/")
    assert res.status_code == 401
    assert set(res.data["error"]) == {"code", "message", "details"}


# --- Exception handler -------------------------------------------------------

def _handle(exc):
    return api_exception_handler(exc, {"view": None, "request": None})


def test_validation_error_format():
    res = _handle(exceptions.ValidationError({"quantity": ["Must be positive."]}))
    assert res.status_code == 400
    assert res.data == {
        "error": {
            "code": "validation_error",
            "message": "Must be positive.",
            "details": {"quantity": ["Must be positive."]},
        }
    }


def test_validation_error_list_and_multi_field():
    res = _handle(exceptions.ValidationError(["Bad thing."]))
    assert res.data["error"]["details"] == {"non_field_errors": ["Bad thing."]}
    res = _handle(exceptions.ValidationError({"a": ["x"], "b": ["y"]}))
    assert res.data["error"]["message"] == "Some of the submitted data is invalid."


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (exceptions.NotAuthenticated(), 401, "not_authenticated"),
        (exceptions.PermissionDenied(), 403, "permission_denied"),
        (DjangoPermissionDenied(), 403, "permission_denied"),
        (exceptions.NotFound(), 404, "not_found"),
        (Http404(), 404, "not_found"),
        (exceptions.MethodNotAllowed("PUT"), 405, "method_not_allowed"),
    ],
)
def test_other_errors_format(exc, status, code):
    res = _handle(exc)
    assert res.status_code == status
    assert res.data["error"]["code"] == code
    assert res.data["error"]["message"]
    assert res.data["error"]["details"] == {}


def test_throttled_has_retry_after():
    res = _handle(exceptions.Throttled(wait=30))
    assert res.status_code == 429
    assert res.data["error"]["code"] == "throttled"
    assert res.data["error"]["details"] == {"retry_after_seconds": 30}


def test_unhandled_error_is_generic_500():
    res = _handle(RuntimeError("secret internals"))
    assert res.status_code == 500
    assert res.data["error"]["code"] == "server_error"
    assert "secret internals" not in str(res.data)


def test_health_check_is_public(api_client):
    res = api_client.get("/api/v1/health/")
    assert res.status_code == 200
    assert res.data == {"status": "ok", "database": "ok"}


# --- Pagination & misc --------------------------------------------------------

def test_pagination_defaults():
    p = StandardPagination()
    assert p.page_size == 20 and p.max_page_size == 100


def test_schema_and_docs_are_public(api_client):
    assert api_client.get("/api/schema/").status_code == 200
    assert api_client.get("/api/docs/").status_code == 200


def test_redact_filter_scrubs_api_key(settings):
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "key=%s", (settings.XAI_API_KEY,), None)
    RedactSecretsFilter().filter(record)
    assert settings.XAI_API_KEY not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()
