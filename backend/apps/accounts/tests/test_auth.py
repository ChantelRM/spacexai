import jwt
import pytest
from django.conf import settings
from django.urls import reverse

from apps.accounts.factories import DEFAULT_TEST_PASSWORD, FarmerFactory
from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

REGISTER = reverse("accounts:register")
LOGIN = reverse("accounts:login")
REFRESH = reverse("accounts:refresh")
LOGOUT = reverse("accounts:logout")
ME = reverse("accounts:me")
CHANGE_PASSWORD = reverse("accounts:change-password")


def _claims(token):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def _register(client, **overrides):
    payload = {
        "email": "Thandi@Example.com",
        "password": "Gr33n-Fields-2026",
        "role": Role.FARMER,
        "display_name": "Thandi's Farm",
        "phone_number": "+27821234567",
    }
    payload.update(overrides)
    return client.post(REGISTER, payload, format="json")


@pytest.mark.parametrize("role", [Role.FARMER, Role.WHOLESALE_BUYER])
def test_register_and_login_for_both_roles(api_client, role):
    res = _register(api_client, role=role)
    assert res.status_code == 201, res.data
    assert res.data["user"]["email"] == "thandi@example.com"  # normalised
    assert res.data["user"]["role"] == role
    assert res.data["role"] == role
    assert _claims(res.data["tokens"]["access"])["role"] == role
    assert "password" not in res.data["user"]

    res = api_client.post(LOGIN, {"email": "THANDI@example.com", "password": "Gr33n-Fields-2026"}, format="json")
    assert res.status_code == 200, res.data
    assert res.data["role"] == role
    assert _claims(res.data["tokens"]["access"])["role"] == role
    assert _claims(res.data["tokens"]["refresh"])["role"] == role


def test_duplicate_email_rejected_case_insensitively(api_client):
    assert _register(api_client).status_code == 201
    res = _register(api_client, email="thandi@EXAMPLE.com")
    assert res.status_code == 400
    assert res.data["error"]["code"] == "validation_error"
    assert "email" in res.data["error"]["details"]
    assert User.objects.count() == 1


@pytest.mark.parametrize("role", ["SUPPLIER", "ADMIN", "", None])
def test_register_rejects_unknown_roles(api_client, role):
    res = _register(api_client, role=role)
    assert res.status_code == 400
    assert "role" in res.data["error"]["details"]


def test_register_validates_password_strength(api_client):
    res = _register(api_client, password="12345")
    assert res.status_code == 400
    assert res.data["error"]["code"] == "validation_error"


def test_login_wrong_password_uses_error_format(api_client, farmer):
    res = api_client.post(LOGIN, {"email": farmer.email, "password": "nope"}, format="json")
    assert res.status_code == 401
    assert res.data["error"]["code"] == "authentication_failed"
    assert res.data["error"]["message"]


def test_refresh_rotates_and_keeps_role(api_client, farmer):
    tokens = api_client.post(LOGIN, {"email": farmer.email, "password": DEFAULT_TEST_PASSWORD}, format="json").data["tokens"]
    res = api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert res.status_code == 200
    assert _claims(res.data["access"])["role"] == Role.FARMER
    assert res.data["refresh"] != tokens["refresh"]
    # The old refresh token is blacklisted after rotation.
    assert api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json").status_code == 401


def test_logout_blacklists_refresh_token(api_client, farmer):
    tokens = api_client.post(LOGIN, {"email": farmer.email, "password": DEFAULT_TEST_PASSWORD}, format="json").data["tokens"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert api_client.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json").status_code == 204
    res = api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert res.status_code == 401
    assert res.data["error"]["code"] == "token_not_valid"


def test_logout_rejects_another_users_token(api_client, farmer, auth_client):
    tokens = api_client.post(LOGIN, {"email": farmer.email, "password": DEFAULT_TEST_PASSWORD}, format="json").data["tokens"]
    other = auth_client(FarmerFactory())
    assert other.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json").status_code == 400


def test_me_requires_auth(api_client):
    res = api_client.get(ME)
    assert res.status_code == 401
    assert res.data["error"]["code"] == "not_authenticated"


def test_me_get_and_patch(farmer_client, farmer):
    res = farmer_client.get(ME)
    assert res.status_code == 200
    assert res.data["email"] == farmer.email
    res = farmer_client.patch(ME, {"display_name": "New Name", "phone_number": "+27830000000"}, format="json")
    assert res.status_code == 200
    assert res.data["display_name"] == "New Name"


def test_me_cannot_change_role_or_email(farmer_client, farmer):
    res = farmer_client.patch(ME, {"role": Role.WHOLESALE_BUYER}, format="json")
    assert res.status_code == 400
    assert "role" in res.data["error"]["details"]
    res = farmer_client.patch(ME, {"email": "other@example.com"}, format="json")
    assert res.status_code == 400
    farmer.refresh_from_db()
    assert farmer.role == Role.FARMER
    # Sending unchanged values back is fine.
    res = farmer_client.patch(ME, {"role": Role.FARMER, "email": farmer.email, "display_name": "X"}, format="json")
    assert res.status_code == 200


def test_me_put_not_allowed(farmer_client):
    assert farmer_client.put(ME, {"display_name": "X"}, format="json").status_code == 405


def test_change_password(api_client, farmer, auth_client):
    tokens = api_client.post(LOGIN, {"email": farmer.email, "password": DEFAULT_TEST_PASSWORD}, format="json").data["tokens"]
    client = auth_client(farmer)
    bad = client.post(CHANGE_PASSWORD, {"old_password": "wrong", "new_password": "An0ther-Good-One"}, format="json")
    assert bad.status_code == 400
    weak = client.post(CHANGE_PASSWORD, {"old_password": DEFAULT_TEST_PASSWORD, "new_password": "123"}, format="json")
    assert weak.status_code == 400
    res = client.post(CHANGE_PASSWORD, {"old_password": DEFAULT_TEST_PASSWORD, "new_password": "An0ther-Good-One"}, format="json")
    assert res.status_code == 200
    assert "access" in res.data and "refresh" in res.data
    # Old refresh tokens are revoked.
    assert api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json").status_code == 401
    assert api_client.post(LOGIN, {"email": farmer.email, "password": "An0ther-Good-One"}, format="json").status_code == 200


def test_create_superuser_requires_role(db):
    with pytest.raises(ValueError):
        User.objects.create_superuser(email="admin@example.com", password="x", display_name="Admin")
    admin = User.objects.create_superuser(
        email="Admin@Example.com", password="x", display_name="Admin", role=Role.FARMER
    )
    assert admin.is_staff and admin.is_superuser and admin.email == "admin@example.com"
