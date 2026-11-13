"""
Shared permission classes. Reuse these in every app instead of re-checking
roles by hand.

    from apps.core.permissions import IsFarmer, IsOwnerOrReadOnly, role_required

    class MyView(APIView):
        permission_classes = [IsFarmer]                          # farmers only
        permission_classes = [role_required("FARMER", "WHOLESALE_BUYER")]
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Role


def has_role(user, *roles) -> bool:
    return bool(user and user.is_authenticated and getattr(user, "role", None) in roles)


def is_owner(user, obj, owner_field: str = "user") -> bool:
    """
    True if ``user`` owns ``obj``. The owner is looked up at
    ``obj.<owner_field>`` (``__`` traverses relations, e.g. ``"order__buyer"``).
    If ``obj`` is itself a User, the user owns only themself.
    """
    from django.contrib.auth import get_user_model

    if not (user and user.is_authenticated):
        return False
    if isinstance(obj, get_user_model()):
        return obj.pk == user.pk
    owner = obj
    for part in owner_field.split("__"):
        owner = getattr(owner, part, None)
    owner_id = getattr(owner, "pk", owner)
    return owner_id is not None and owner_id == user.pk


class IsFarmer(BasePermission):
    message = "Only farmer accounts can perform this action."

    def has_permission(self, request, view):
        return has_role(request.user, Role.FARMER)


class IsWholesaleBuyer(BasePermission):
    message = "Only wholesale buyer accounts can perform this action."

    def has_permission(self, request, view):
        return has_role(request.user, Role.WHOLESALE_BUYER)


class IsOwnerOrReadOnly(BasePermission):
    """
    Object-level: authenticated users may read; only the owner may write.
    Set ``owner_field`` on the view if the owner FK is not called ``user``.
    """

    message = "You can only change your own records."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return is_owner(request.user, obj, getattr(view, "owner_field", "user"))


class IsOwner(BasePermission):
    """Object-level: only the owner may read or write."""

    message = "You do not have access to this record."

    def has_object_permission(self, request, view, obj):
        return is_owner(request.user, obj, getattr(view, "owner_field", "user"))


def role_required(*roles):
    """Build a permission class that allows only the given role values."""
    unknown = set(roles) - set(Role.values)
    if not roles or unknown:
        raise ValueError(f"role_required() needs valid roles, got: {roles}")

    class RoleRequired(BasePermission):
        message = "Your account type cannot perform this action."

        def has_permission(self, request, view):
            return has_role(request.user, *roles)

    RoleRequired.__name__ = "RoleRequired_" + "_".join(roles)
    RoleRequired.allowed_roles = frozenset(roles)
    return RoleRequired
