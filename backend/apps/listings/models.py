from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

from .units import Unit, produce_key

MONEY = {"max_digits": 12, "decimal_places": 2}
QUANTITY = {"max_digits": 12, "decimal_places": 2}


class QualityGrade(models.TextChoices):
    PREMIUM = "PREMIUM", "Premium"
    ORGANIC = "ORGANIC", "Organic"
    GRADE_A = "GRADE_A", "Grade A"
    GRADE_B = "GRADE_B", "Grade B"
    STANDARD = "STANDARD", "Standard"


# Higher is better. Used for "minimum quality" filters and scoring.
QUALITY_RANK = {
    QualityGrade.STANDARD: 1,
    QualityGrade.GRADE_B: 2,
    QualityGrade.GRADE_A: 3,
    QualityGrade.ORGANIC: 3,
    QualityGrade.PREMIUM: 4,
}


def meets_quality(grade, minimum) -> bool:
    if not minimum:
        return True
    return QUALITY_RANK.get(grade, 0) >= QUALITY_RANK.get(minimum, 0)


class ProduceCategory(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "produce categories"

    def __str__(self):
        return self.name


class ListingStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    SOLD_OUT = "SOLD_OUT", "Sold out"
    DELETED = "DELETED", "Deleted"


class ProduceListingQuerySet(models.QuerySet):
    def not_deleted(self):
        return self.exclude(status=ListingStatus.DELETED)

    def active(self, on_date=None):
        """Visible in the marketplace: ACTIVE, in stock and not past available_until."""
        on_date = on_date or timezone.localdate()
        return self.filter(status=ListingStatus.ACTIVE, quantity_available__gt=0).filter(
            models.Q(available_until__isnull=True) | models.Q(available_until__gte=on_date)
        )


class ProduceListing(TimeStampedModel):
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="produce_listings")
    produce_name = models.CharField(max_length=80)
    produce_key = models.CharField(max_length=80, db_index=True, editable=False)
    category = models.ForeignKey(ProduceCategory, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="listings")
    quantity_available = models.DecimalField(**QUANTITY, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=8, choices=Unit.choices)
    price_per_unit = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    quality_grade = models.CharField(max_length=10, choices=QualityGrade.choices, default=QualityGrade.STANDARD)
    available_from = models.DateField(default=timezone.localdate)
    available_until = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=10, choices=ListingStatus.choices, default=ListingStatus.ACTIVE,
                              db_index=True)

    objects = ProduceListingQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity_available__gte=0), name="listing_quantity_gte_0"),
            models.CheckConstraint(condition=models.Q(price_per_unit__gte=0), name="listing_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.produce_name} ({self.quantity_available} {self.unit}) by {self.farmer_id}"

    def save(self, *args, **kwargs):
        self.produce_key = produce_key(self.produce_name)
        # Keep status in step with stock (never touches PAUSED/DELETED).
        if self.status == ListingStatus.ACTIVE and self.quantity_available <= 0:
            self.status = ListingStatus.SOLD_OUT
        elif self.status == ListingStatus.SOLD_OUT and self.quantity_available > 0:
            self.status = ListingStatus.ACTIVE
        if kwargs.get("update_fields"):
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"produce_key", "status", "updated_at"}
        super().save(*args, **kwargs)


def listing_image_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"listings/{instance.listing_id}/{timezone.now():%Y%m%d%H%M%S%f}.{ext}"


class ListingImage(models.Model):
    listing = models.ForeignKey(ProduceListing, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=listing_image_path)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Image {self.pk} for listing {self.listing_id}"
