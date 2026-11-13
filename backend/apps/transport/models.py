from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.listings.models import MONEY, QUANTITY
from apps.locations.models import Province


class SplitMethod(models.TextChoices):
    WEIGHT = "WEIGHT", "By weight"
    VOLUME = "VOLUME", "By volume"
    DISTANCE = "DISTANCE", "By distance to destination"
    SPACE = "SPACE", "By space used"
    EQUAL = "EQUAL", "Equal split"
    AGREED = "AGREED", "Agreed amounts"


class TransportStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    FULL = "FULL", "Full"
    CONFIRMED = "CONFIRMED", "Confirmed"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class TransportRequest(TimeStampedModel):
    organiser = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transport_organised")
    pickup_province = models.CharField(max_length=20, choices=Province.choices)
    pickup_municipality = models.CharField(max_length=120)
    pickup_town = models.CharField(max_length=120)
    destination = models.CharField(max_length=200, help_text="e.g. Johannesburg Fresh Produce Market")
    destination_town = models.CharField(max_length=120)
    destination_municipality = models.CharField(max_length=120, blank=True)
    destination_province = models.CharField(max_length=20, choices=Province.choices)
    # Public place (e.g. a market), so coordinates here are not private. Optional.
    destination_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                               validators=[MinValueValidator(-90), MaxValueValidator(90)])
    destination_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                                validators=[MinValueValidator(-180), MaxValueValidator(180)])
    travel_date = models.DateField()
    vehicle_description = models.CharField(max_length=200, blank=True)
    total_cost = models.DecimalField(**MONEY, null=True, blank=True, validators=[MinValueValidator(0)],
                                     help_text="Leave empty until quoted")
    capacity = models.DecimalField(**QUANTITY, null=True, blank=True, validators=[MinValueValidator(0)])
    capacity_unit = models.CharField(max_length=10, blank=True, default="KG", help_text="KG, M3 or SPACES")
    cost_split_method = models.CharField(max_length=8, choices=SplitMethod.choices, default=SplitMethod.WEIGHT)
    notes = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=10, choices=TransportStatus.choices, default=TransportStatus.OPEN,
                              db_index=True)

    class Meta:
        ordering = ["travel_date", "-created_at"]


class TransportParticipant(TimeStampedModel):
    request = models.ForeignKey(TransportRequest, on_delete=models.CASCADE, related_name="participants")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transport_trips")
    load_weight_kg = models.DecimalField(**QUANTITY, null=True, blank=True, validators=[MinValueValidator(0)])
    load_volume_m3 = models.DecimalField(**QUANTITY, null=True, blank=True, validators=[MinValueValidator(0)])
    load_space_units = models.DecimalField(**QUANTITY, null=True, blank=True, validators=[MinValueValidator(0)])
    pickup_town = models.CharField(max_length=120, blank=True)
    agreed_amount = models.DecimalField(**MONEY, null=True, blank=True, validators=[MinValueValidator(0)])
    calculated_share = models.DecimalField(**MONEY, null=True, blank=True)
    confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["request", "farmer"], name="unique_transport_participant")]
