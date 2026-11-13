from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.listings.models import MONEY, QUANTITY, ProduceCategory, QualityGrade
from apps.listings.units import Unit, produce_key


class BusinessType(models.TextChoices):
    RESTAURANT = "RESTAURANT", "Restaurant"
    SUPERMARKET = "SUPERMARKET", "Supermarket"
    GROCERY = "GROCERY", "Grocery store"
    DISTRIBUTOR = "DISTRIBUTOR", "Distributor"
    PROCESSOR = "PROCESSOR", "Processor"
    WHOLESALER = "WHOLESALER", "Wholesaler"
    OTHER = "OTHER", "Other"


class WholesaleBuyerProfile(TimeStampedModel):
    """Business details for a WHOLESALE_BUYER user. Location and delivery areas live on UserLocation."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buyer_profile")
    business_name = models.CharField(max_length=120)
    business_type = models.CharField(max_length=12, choices=BusinessType.choices, default=BusinessType.OTHER)
    description = models.TextField(blank=True, max_length=2000)
    produce_interests = models.JSONField(default=list, blank=True, help_text="Produce names or category slugs")

    def __str__(self):
        return f"{self.business_name} ({self.user_id})"


class Recurrence(models.TextChoices):
    NONE = "NONE", "One-off"
    WEEKLY = "WEEKLY", "Weekly"
    MONTHLY = "MONTHLY", "Monthly"


class RequirementStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    FULFILLED = "FULFILLED", "Fulfilled"
    CLOSED = "CLOSED", "Closed"


class BuyerRequirement(TimeStampedModel):
    """A buyer's produce need. Farmers are matched to OPEN requirements."""

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="requirements")
    produce_name = models.CharField(max_length=80)
    produce_key = models.CharField(max_length=80, db_index=True, editable=False)
    category = models.ForeignKey(ProduceCategory, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="requirements")
    quantity_needed = models.DecimalField(**QUANTITY, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=8, choices=Unit.choices)
    max_price_per_unit = models.DecimalField(**MONEY, null=True, blank=True, validators=[MinValueValidator(0)])
    min_quality_grade = models.CharField(max_length=10, choices=QualityGrade.choices, blank=True)
    needed_by = models.DateField()
    max_distance_km = models.PositiveIntegerField(null=True, blank=True)
    recurring = models.CharField(max_length=8, choices=Recurrence.choices, default=Recurrence.NONE)
    notes = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=10, choices=RequirementStatus.choices, default=RequirementStatus.OPEN,
                              db_index=True)

    class Meta:
        ordering = ["needed_by", "-created_at"]

    def __str__(self):
        return f"{self.quantity_needed} {self.unit} {self.produce_name} by {self.needed_by}"

    def save(self, *args, **kwargs):
        self.produce_key = produce_key(self.produce_name)
        super().save(*args, **kwargs)
