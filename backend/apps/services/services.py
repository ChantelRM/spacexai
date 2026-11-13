"""Shared security costs, security alerts and insurance information."""
from __future__ import annotations

import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core.costs import allocate, to_cents
from apps.core.notifications import notify
from apps.groups.services import is_active_member
from apps.locations.distance import _norm
from apps.locations.models import UserLocation

from .models import (
    SecurityAlert,
    ServiceContribution,
    ServiceSplit,
    ServiceStatus,
    SharedServiceRequest,
)

# Alerts share information, never personal data about suspects.
_SA_ID = re.compile(r"\b\d{13}\b")
_PHONE = re.compile(r"(\+27|\b0)[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{4}\b")


def check_alert_text(text: str):
    if _SA_ID.search(text) or _PHONE.search(text):
        raise ValidationError({"body": ["Don't include ID or phone numbers. Share what happened, where and when; "
                                        "report suspects to SAPS (10111) instead."]})


def get_service(service_id, *, for_update=False) -> SharedServiceRequest:
    qs = SharedServiceRequest.objects.select_related("organiser")
    if for_update:
        qs = qs.select_for_update()
    obj = qs.filter(pk=service_id).first()
    if obj is None:
        raise NotFound("Shared service not found.")
    return obj


def compute_contributions(service) -> dict:
    contribs = list(service.contributions.all())
    if service.total_monthly_cost is None or not contribs:
        return {"amounts": {c.pk: None for c in contribs}, "problem": "Waiting for the monthly cost."
                if service.total_monthly_cost is None else None}
    if service.split_method == ServiceSplit.AGREED:
        if any(c.agreed_amount is None for c in contribs):
            return {"amounts": {c.pk: None for c in contribs}, "problem": "Not everyone has an agreed amount yet."}
        total = to_cents(sum(c.agreed_amount for c in contribs))
        if total != to_cents(service.total_monthly_cost):
            return {"amounts": {c.pk: None for c in contribs},
                    "problem": f"Agreed amounts add up to R{total}, but the monthly cost is "
                               f"R{to_cents(service.total_monthly_cost)}."}
        return {"amounts": {c.pk: to_cents(c.agreed_amount) for c in contribs}, "problem": None}
    return {"amounts": dict(zip([c.pk for c in contribs], allocate(service.total_monthly_cost, [1] * len(contribs)))),
            "problem": None}


def _recalculate(service, changed_by=None):
    result = compute_contributions(service)
    for c in service.contributions.all():
        new = result["amounts"].get(c.pk)
        if new != c.amount:
            was_confirmed = c.confirmed
            c.amount, c.confirmed, c.confirmed_at = new, False, None
            c.save(update_fields=["amount", "confirmed", "confirmed_at", "updated_at"])
            if was_confirmed and c.farmer_id != getattr(changed_by, "pk", None):
                notify(c.farmer, "service_recalculated", f"Your share of {service.title} changed. Please confirm again.",
                       f"services/{service.pk}")
    return result


@transaction.atomic
def create_service(user, **data) -> SharedServiceRequest:
    if data.get("group") and not is_active_member(data["group"], user):
        raise PermissionDenied("You can only organise this for a group you belong to.")
    service = SharedServiceRequest.objects.create(organiser=user, **data)
    ServiceContribution.objects.create(request=service, farmer=user)
    _recalculate(service, user)
    return service


@transaction.atomic
def join(user, service_id, agreed_amount=None) -> ServiceContribution:
    service = get_service(service_id, for_update=True)
    if service.status == ServiceStatus.CLOSED:
        raise ValidationError("This shared service is closed.")
    if service.group_id and not is_active_member(service.group, user):
        raise PermissionDenied("This shared service is for members of its group.")
    c, _ = ServiceContribution.objects.update_or_create(request=service, farmer=user,
                                                        defaults={"agreed_amount": agreed_amount})
    _recalculate(service, user)
    c.refresh_from_db()
    return c


@transaction.atomic
def leave(user, service_id):
    service = get_service(service_id, for_update=True)
    if not ServiceContribution.objects.filter(request=service, farmer=user).delete()[0]:
        raise ValidationError("You haven't joined this shared service.")
    _recalculate(service, user)


@transaction.atomic
def update_cost(user, service_id, *, total_monthly_cost=None, split_method=None) -> SharedServiceRequest:
    service = get_service(service_id, for_update=True)
    if service.organiser_id != user.pk:
        raise PermissionDenied("Only the organiser can set the cost.")
    if total_monthly_cost is not None:
        service.total_monthly_cost = total_monthly_cost
    if split_method:
        service.split_method = split_method
    service.save()
    _recalculate(service, user)
    return service


@transaction.atomic
def confirm(user, service_id) -> ServiceContribution:
    service = get_service(service_id, for_update=True)
    c = ServiceContribution.objects.filter(request=service, farmer=user).first()
    if c is None:
        raise ValidationError("Join before confirming.")
    if c.amount is None:
        raise ValidationError(compute_contributions(service)["problem"] or "Your contribution isn't calculated yet.")
    c.confirmed, c.confirmed_at = True, timezone.now()
    c.save(update_fields=["confirmed", "confirmed_at", "updated_at"])
    if not service.contributions.filter(confirmed=False).exists() and service.status == ServiceStatus.OPEN:
        service.status = ServiceStatus.ACTIVE
        service.save(update_fields=["status", "updated_at"])
    return c


def visible_alerts(user):
    """Alerts in the user's municipality, plus alerts posted to their groups."""
    loc = UserLocation.objects.filter(user=user).first()
    area = Q(group__isnull=True, province=loc.province, municipality__iexact=loc.municipality) if loc else Q(pk__in=[])
    groups = Q(group__memberships__farmer=user, group__memberships__status="ACTIVE")
    return SecurityAlert.objects.filter(area | groups | Q(author=user)).distinct().select_related("author")


def create_alert(user, **data) -> SecurityAlert:
    check_alert_text(f"{data.get('title', '')} {data.get('body', '')}")
    group = data.get("group")
    if group and not is_active_member(group, user):
        raise PermissionDenied("You can only post to groups you belong to.")
    alert = SecurityAlert.objects.create(author=user, **data)
    recipients = UserLocation.objects.filter(province=alert.province).exclude(user=user).select_related("user")
    for loc in recipients:
        if _norm(loc.municipality) == _norm(alert.municipality) and loc.user.role == "FARMER":
            notify(loc.user, "security_alert", f"Security alert near {alert.town or alert.municipality}: {alert.title}",
                   f"security/alerts/{alert.pk}")
    return alert
