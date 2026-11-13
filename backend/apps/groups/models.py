from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.locations.models import Province


class GroupType(models.TextChoices):
    LOCATION = "LOCATION", "Local farmers"
    PRODUCE = "PRODUCE", "Produce"
    INTEREST = "INTEREST", "Interest"
    PURCHASING = "PURCHASING", "Group purchasing"
    TRANSPORT = "TRANSPORT", "Transport"


class FarmerGroup(TimeStampedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=2000)
    group_type = models.CharField(max_length=10, choices=GroupType.choices, default=GroupType.LOCATION)
    focus = models.CharField(max_length=80, blank=True, help_text="Produce or interest, e.g. 'poultry', 'security'")
    province = models.CharField(max_length=20, choices=Province.choices)
    municipality = models.CharField(max_length=120)
    town = models.CharField(max_length=120, blank=True)
    is_open = models.BooleanField(default=True, help_text="Open: anyone joins at once. Closed: admins approve.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MembershipRole(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    MEMBER = "MEMBER", "Member"


class MembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INVITED = "INVITED", "Invited"
    REQUESTED = "REQUESTED", "Requested to join"
    LEFT = "LEFT", "Left"
    REMOVED = "REMOVED", "Removed"


class GroupMembership(TimeStampedModel):
    group = models.ForeignKey(FarmerGroup, on_delete=models.CASCADE, related_name="memberships")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_memberships")
    role = models.CharField(max_length=6, choices=MembershipRole.choices, default=MembershipRole.MEMBER)
    status = models.CharField(max_length=10, choices=MembershipStatus.choices, db_index=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "farmer"], name="unique_group_membership")]


class GroupPost(TimeStampedModel):
    group = models.ForeignKey(FarmerGroup, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField(max_length=4000)
    is_announcement = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_announcement", "-created_at"]
