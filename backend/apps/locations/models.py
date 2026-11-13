from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Province(models.TextChoices):
    EASTERN_CAPE = "EASTERN_CAPE", "Eastern Cape"
    FREE_STATE = "FREE_STATE", "Free State"
    GAUTENG = "GAUTENG", "Gauteng"
    KWAZULU_NATAL = "KWAZULU_NATAL", "KwaZulu-Natal"
    LIMPOPO = "LIMPOPO", "Limpopo"
    MPUMALANGA = "MPUMALANGA", "Mpumalanga"
    NORTHERN_CAPE = "NORTHERN_CAPE", "Northern Cape"
    NORTH_WEST = "NORTH_WEST", "North West"
    WESTERN_CAPE = "WESTERN_CAPE", "Western Cape"


class UserLocation(TimeStampedModel):
    """
    Where a user farms or buys. One per user (``user.location``).

    PRIVACY: ``latitude``/``longitude`` are only ever shown to the owner.
    Everyone else sees province, municipality, town and an approximate
    distance (see ``apps.locations.distance`` and
    ``apps.locations.serializers.public_location``).
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="location")
    province = models.CharField(max_length=20, choices=Province.choices, db_index=True)
    municipality = models.CharField(max_length=120, help_text="District or local municipality")
    town = models.CharField(max_length=120, help_text="Town, village or city")
    address_line = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    share_precise_location = models.BooleanField(
        default=False,
        help_text=(
            "Reserved for a future, explicit sharing rule. Exact coordinates are "
            "currently never shown to other users whatever this is set to."
        ),
    )
    preferred_delivery_areas = models.JSONField(
        default=list, blank=True,
        help_text='List of {"province", "municipality", "town"} (mainly for buyers).',
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__isnull=True, longitude__isnull=True)
                | Q(latitude__isnull=False, longitude__isnull=False),
                name="userlocation_lat_lng_both_or_neither",
            ),
        ]

    def __str__(self):
        return f"{self.town}, {self.municipality}, {self.get_province_display()} ({self.user_id})"

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def clean(self):
        super().clean()
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("Latitude and longitude must both be set or both be empty.")
