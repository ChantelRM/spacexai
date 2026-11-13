from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.listings.models import MONEY
from apps.locations.models import Province

INSURANCE_DISCLAIMER = (
    "Information only. This platform is not an insurer or financial services provider and does not "
    "sell, arrange or confirm insurance. Nothing here means you are covered. Cover exists only once an "
    "authorised provider issues you a policy. Check that a provider is FSCA-authorised before buying."
)


class ServiceType(models.TextChoices):
    SECURITY = "SECURITY", "Shared security"
    OTHER = "OTHER", "Other shared service"


class ServiceSplit(models.TextChoices):
    EQUAL = "EQUAL", "Equal split"
    AGREED = "AGREED", "Agreed amounts"


class ServiceStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    ACTIVE = "ACTIVE", "Active"
    CLOSED = "CLOSED", "Closed"


class SharedServiceRequest(TimeStampedModel):
    """e.g. farmers in an area sharing a security guard or patrol."""

    organiser = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    service_type = models.CharField(max_length=10, choices=ServiceType.choices, default=ServiceType.SECURITY)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=2000)
    province = models.CharField(max_length=20, choices=Province.choices)
    municipality = models.CharField(max_length=120)
    town = models.CharField(max_length=120, blank=True)
    group = models.ForeignKey("groups.FarmerGroup", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="shared_services")
    total_monthly_cost = models.DecimalField(**MONEY, null=True, blank=True, validators=[MinValueValidator(0)])
    split_method = models.CharField(max_length=6, choices=ServiceSplit.choices, default=ServiceSplit.EQUAL)
    status = models.CharField(max_length=6, choices=ServiceStatus.choices, default=ServiceStatus.OPEN)

    class Meta:
        ordering = ["-created_at"]


class ServiceContribution(TimeStampedModel):
    request = models.ForeignKey(SharedServiceRequest, on_delete=models.CASCADE, related_name="contributions")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    agreed_amount = models.DecimalField(**MONEY, null=True, blank=True, validators=[MinValueValidator(0)])
    amount = models.DecimalField(**MONEY, null=True, blank=True, help_text="Calculated monthly contribution")
    confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["request", "farmer"], name="unique_service_contribution")]


class AlertType(models.TextChoices):
    THEFT = "THEFT", "Theft"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY", "Suspicious activity"
    LIVESTOCK = "LIVESTOCK", "Livestock theft or loss"
    FIRE = "FIRE", "Fire"
    OTHER = "OTHER", "Other"


class SecurityAlert(TimeStampedModel):
    """Information-sharing post scoped to an area or group. Never personal data about suspects."""

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    alert_type = models.CharField(max_length=20, choices=AlertType.choices, default=AlertType.OTHER)
    title = models.CharField(max_length=120)
    body = models.TextField(max_length=2000)
    province = models.CharField(max_length=20, choices=Province.choices)
    municipality = models.CharField(max_length=120)
    town = models.CharField(max_length=120, blank=True)
    group = models.ForeignKey("groups.FarmerGroup", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class InsuranceCategory(models.TextChoices):
    CROP = "CROP", "Crop"
    LIVESTOCK = "LIVESTOCK", "Livestock"
    EQUIPMENT = "EQUIPMENT", "Equipment"
    PROPERTY = "PROPERTY", "Property"


class InsuranceProduct(TimeStampedModel):
    """Admin-managed information about insurance products. The platform does not sell insurance."""

    provider_name = models.CharField(max_length=120)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=10, choices=InsuranceCategory.choices)
    summary = models.TextField(max_length=2000)
    provider_contact = models.CharField(max_length=200, blank=True)
    website = models.URLField(blank=True)
    is_authorised_provider = models.BooleanField(default=False, help_text="Admin has checked FSCA authorisation")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "provider_name"]

    def __str__(self):
        return f"{self.provider_name}: {self.name}"


class QuoteStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    QUOTED = "QUOTED", "Quote received"
    CLOSED = "CLOSED", "Closed"


class InsuranceQuoteRequest(TimeStampedModel):
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    product = models.ForeignKey(InsuranceProduct, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=10, choices=InsuranceCategory.choices)
    details = models.TextField(max_length=2000)
    status = models.CharField(max_length=10, choices=QuoteStatus.choices, default=QuoteStatus.SUBMITTED)
    quote_note = models.TextField(blank=True, max_length=2000, help_text="Entered by an admin")
    quote_amount = models.DecimalField(**MONEY, null=True, blank=True, help_text="Entered by an admin")

    class Meta:
        ordering = ["-created_at"]
