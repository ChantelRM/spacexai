from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class FarmerProfile(TimeStampedModel):
    """Farm details for a FARMER user. Location lives on UserLocation, contact details on User."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="farmer_profile")
    farm_name = models.CharField(max_length=120)
    bio = models.TextField(blank=True, max_length=2000)
    farm_size_hectares = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                             validators=[MinValueValidator(0)])
    main_produce = models.JSONField(default=list, blank=True, help_text="List of produce names, e.g. ['Tomatoes']")
    is_verified = models.BooleanField(default=False, help_text="Set by platform admins only.")

    def __str__(self):
        return f"{self.farm_name} ({self.user_id})"
