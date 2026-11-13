from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.listings.models import MONEY, QUANTITY


class EquipmentType(models.TextChoices):
    TRACTOR = "TRACTOR", "Tractor"
    IRRIGATION = "IRRIGATION", "Irrigation"
    HARVESTER = "HARVESTER", "Harvester"
    TOOLS = "TOOLS", "Tools"
    COLD_STORAGE = "COLD_STORAGE", "Cold storage"
    WAREHOUSE = "WAREHOUSE", "Warehouse"
    MACHINERY = "MACHINERY", "Machinery"
    OTHER = "OTHER", "Other"


STORAGE_TYPES = {EquipmentType.COLD_STORAGE, EquipmentType.WAREHOUSE}


class RateUnit(models.TextChoices):
    PER_HOUR = "PER_HOUR", "per hour"
    PER_DAY = "PER_DAY", "per day"
    PER_MONTH = "PER_MONTH", "per month"
    PER_TONNE_PER_DAY = "PER_TONNE_PER_DAY", "per tonne per day"


class EquipmentListing(TimeStampedModel):
    """Equipment or storage a farmer offers. Location comes from the owner's UserLocation."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="equipment")
    type = models.CharField(max_length=12, choices=EquipmentType.choices)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=2000)
    rate = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    rate_unit = models.CharField(max_length=17, choices=RateUnit.choices, default=RateUnit.PER_DAY)
    capacity = models.DecimalField(**QUANTITY, null=True, blank=True, validators=[MinValueValidator(0)],
                                   help_text="Storage capacity in tonnes")
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_storage(self) -> bool:
        return self.type in STORAGE_TYPES


class BookingStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    APPROVED = "APPROVED", "Approved"
    DECLINED = "DECLINED", "Declined"
    CANCELLED = "CANCELLED", "Cancelled"
    COMPLETED = "COMPLETED", "Completed"


class EquipmentBooking(TimeStampedModel):
    listing = models.ForeignKey(EquipmentListing, on_delete=models.CASCADE, related_name="bookings")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="equipment_bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    quantity = models.DecimalField(**QUANTITY, null=True, blank=True, validators=[MinValueValidator(0)],
                                   help_text="Storage tonnes requested")
    status = models.CharField(max_length=10, choices=BookingStatus.choices, default=BookingStatus.REQUESTED,
                              db_index=True)
    estimated_cost = models.DecimalField(**MONEY, default=0)
    notes = models.TextField(blank=True, max_length=1000)

    class Meta:
        ordering = ["start"]
        constraints = [models.CheckConstraint(condition=models.Q(end__gt=models.F("start")),
                                              name="booking_end_after_start")]
