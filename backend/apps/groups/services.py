"""Farmer group rules: joining, invitations, admin management, posts. At least one admin always remains."""
from __future__ import annotations

from types import SimpleNamespace

from django.db import transaction
from django.db.models import Count, Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import Role, User
from apps.core.notifications import notify
from apps.listings.units import produce_key, produce_matches
from apps.locations.distance import approximate_distance, proximity_rank, within_km
from apps.locations.models import UserLocation

from .models import FarmerGroup, GroupMembership, GroupPost, MembershipRole, MembershipStatus

A, M = MembershipRole.ADMIN, MembershipRole.MEMBER
ST = MembershipStatus


def area_of(group):
    """Groups have an area, not coordinates: used for proximity tiers."""
    return SimpleNamespace(province=group.province, municipality=group.municipality, town=group.town,
                           latitude=None, longitude=None)


def get_group(group_id) -> FarmerGroup:
    group = FarmerGroup.objects.filter(pk=group_id).first()
    if group is None:
        raise NotFound("Group not found.")
    return group


def membership(group, user):
    return GroupMembership.objects.filter(group=group, farmer=user).first()


def is_active_member(group, user) -> bool:
    return GroupMembership.objects.filter(group=group, farmer=user, status=ST.ACTIVE).exists()


def require_admin(group, user):
    if not GroupMembership.objects.filter(group=group, farmer=user, status=ST.ACTIVE, role=A).exists():
        raise PermissionDenied("Only group admins can do that.")


def _admin_count(group) -> int:
    return GroupMembership.objects.filter(group=group, status=ST.ACTIVE, role=A).count()


def _set(m, status, role=None, invited_by=None):
    m.status = status
    if role:
        m.role = role
    if invited_by is not None:
        m.invited_by = invited_by
    m.save()
    return m


@transaction.atomic
def create_group(user, **data) -> FarmerGroup:
    group = FarmerGroup.objects.create(created_by=user, **data)
    GroupMembership.objects.create(group=group, farmer=user, role=A, status=ST.ACTIVE)
    return group


@transaction.atomic
def join(user, group_id) -> GroupMembership:
    group = get_group(group_id)
    m = membership(group, user)
    if m and m.status == ST.ACTIVE:
        raise ValidationError("You are already a member of this group.")
    if m and m.status == ST.REQUESTED:
        raise ValidationError("Your request to join is waiting for an admin.")
    if m and m.status == ST.REMOVED:
        raise PermissionDenied("You were removed from this group.")
    invited = m is not None and m.status == ST.INVITED
    status = ST.ACTIVE if (group.is_open or invited) else ST.REQUESTED
    if m is None:
        m = GroupMembership.objects.create(group=group, farmer=user, role=M, status=status)
    else:
        _set(m, status, role=M)
    if status == ST.REQUESTED:
        for admin in GroupMembership.objects.filter(group=group, status=ST.ACTIVE, role=A).select_related("farmer"):
            notify(admin.farmer, "group_join_request", f"{user.display_name} asked to join {group.name}.",
                   f"groups/{group.pk}")
    return m


@transaction.atomic
def invite(admin, group_id, farmer_id) -> GroupMembership:
    group = get_group(group_id)
    require_admin(group, admin)
    farmer = User.objects.filter(pk=farmer_id, role=Role.FARMER, is_active=True).first()
    if farmer is None:
        raise ValidationError({"farmer_id": ["Farmer not found."]})
    m = membership(group, farmer)
    if m and m.status in (ST.ACTIVE, ST.INVITED):
        raise ValidationError("This farmer is already a member or invited.")
    if m and m.status == ST.REQUESTED:
        return _set(m, ST.ACTIVE)  # inviting someone who asked = approving them
    if m is None:
        m = GroupMembership.objects.create(group=group, farmer=farmer, role=M, status=ST.INVITED, invited_by=admin)
    else:
        _set(m, ST.INVITED, role=M, invited_by=admin)
    notify(farmer, "group_invite", f"{admin.display_name} invited you to join {group.name}.", f"groups/{group.pk}")
    return m


@transaction.atomic
def respond_to_invite(user, group_id, accept: bool) -> GroupMembership:
    group = get_group(group_id)
    m = membership(group, user)
    if m is None or m.status != ST.INVITED:
        raise ValidationError("You have no pending invitation to this group.")
    if accept:
        return _set(m, ST.ACTIVE)
    m.delete()
    return GroupMembership(group=group, farmer=user, role=M, status=ST.LEFT)


@transaction.atomic
def decide_request(admin, group_id, farmer_id, approve: bool) -> GroupMembership:
    group = get_group(group_id)
    require_admin(group, admin)
    m = GroupMembership.objects.filter(group=group, farmer_id=farmer_id, status=ST.REQUESTED).first()
    if m is None:
        raise NotFound("Join request not found.")
    if approve:
        _set(m, ST.ACTIVE)
        notify(m.farmer, "group_join_approved", f"You joined {group.name}.", f"groups/{group.pk}")
        return m
    m.delete()
    return GroupMembership(group=group, farmer_id=farmer_id, role=M, status=ST.REMOVED)


def _ensure_admin_remains(group, leaving_membership):
    if leaving_membership.role != A or _admin_count(group) > 1:
        return
    others = GroupMembership.objects.filter(group=group, status=ST.ACTIVE).exclude(pk=leaving_membership.pk)
    if others.exists():
        raise ValidationError("A group needs at least one admin. Make another member an admin first.")


@transaction.atomic
def leave(user, group_id):
    group = get_group(group_id)
    m = membership(group, user)
    if m is None or m.status != ST.ACTIVE:
        raise ValidationError("You are not a member of this group.")
    _ensure_admin_remains(group, m)
    return _set(m, ST.LEFT, role=M)


@transaction.atomic
def remove_member(admin, group_id, farmer_id):
    group = get_group(group_id)
    require_admin(group, admin)
    m = GroupMembership.objects.filter(group=group, farmer_id=farmer_id, status=ST.ACTIVE).first()
    if m is None:
        raise NotFound("Member not found.")
    if m.farmer_id == admin.pk:
        raise ValidationError("Use leave to leave the group yourself.")
    _ensure_admin_remains(group, m)
    return _set(m, ST.REMOVED, role=M)


@transaction.atomic
def set_role(admin, group_id, farmer_id, role):
    group = get_group(group_id)
    require_admin(group, admin)
    m = GroupMembership.objects.filter(group=group, farmer_id=farmer_id, status=ST.ACTIVE).first()
    if m is None:
        raise NotFound("Member not found.")
    if role == M and m.role == A and _admin_count(group) == 1:
        raise ValidationError("A group needs at least one admin.")
    return _set(m, ST.ACTIVE, role=role)


def create_post(user, group_id, body, is_announcement=False) -> GroupPost:
    group = get_group(group_id)
    if not is_active_member(group, user):
        raise PermissionDenied("Only members can post in this group.")
    if is_announcement:
        require_admin(group, user)
    post = GroupPost.objects.create(group=group, author=user, body=body.strip(), is_announcement=is_announcement)
    if is_announcement:
        for m in GroupMembership.objects.filter(group=group, status=ST.ACTIVE).exclude(farmer=user):
            notify(m.farmer, "group_announcement", f"{group.name}: {post.body[:120]}", f"groups/{group.pk}")
    return post


def list_posts(user, group_id):
    group = get_group(group_id)
    if not is_active_member(group, user):
        raise PermissionDenied("Only members can read this group's posts.")
    return group.posts.select_related("author")


def search_groups(user, *, q=None, group_type=None, province=None, municipality=None, town=None, focus=None,
                  max_distance_km=None, mine=False):
    qs = FarmerGroup.objects.annotate(
        member_count=Count("memberships", filter=Q(memberships__status=ST.ACTIVE)))
    if mine:
        qs = qs.filter(memberships__farmer=user, memberships__status=ST.ACTIVE)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(focus__icontains=q))
    if group_type:
        qs = qs.filter(group_type=group_type)
    if province:
        qs = qs.filter(province=province)
    if municipality:
        qs = qs.filter(municipality__iexact=municipality.strip())
    if town:
        qs = qs.filter(town__iexact=town.strip())
    groups = list(qs[:1000])
    if focus:
        key = produce_key(focus)
        groups = [g for g in groups if produce_matches(produce_key(g.focus), key) or key in produce_key(g.name)
                  or key in produce_key(g.description)]
    origin = UserLocation.objects.filter(user=user).first()
    if max_distance_km is not None:
        groups = [g for g in groups if within_km(origin, area_of(g), max_distance_km)]
    groups.sort(key=lambda g: (proximity_rank(origin, area_of(g)), g.name))
    my_status = dict(GroupMembership.objects.filter(farmer=user, group__in=groups).values_list("group_id", "status"))
    for g in groups:
        g.distance = approximate_distance(origin, area_of(g))
        g.my_status = my_status.get(g.pk)
    return groups


def find_farmer_groups(user, *, focus=None, max_distance_km=None, limit=10, **_ignored) -> dict:
    """AI contract: services_contract.FindFarmerGroups."""
    if user.role != Role.FARMER:
        raise PermissionDenied("Farmer groups are for farmers.")
    groups = search_groups(user, focus=focus, max_distance_km=max_distance_km)[:limit]
    results = [{
        "group_id": g.pk, "name": g.name, "group_type": g.group_type, "focus": g.focus,
        "member_count": g.member_count, "is_open": g.is_open,
        "area": {"province": g.province, "municipality": g.municipality, "town": g.town, "distance": g.distance},
        "is_member": g.my_status == ST.ACTIVE, "my_status": g.my_status,
    } for g in groups]
    out = {"available": True, "count": len(results), "results": results}
    if not results:
        out["message"] = "No farmer groups match that yet. You can start one in the Co-op hub."
    return out
