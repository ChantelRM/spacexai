from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.listings.models import MONEY, QUANTITY


class BulkCategory(models.TextChoices):
    FERTILISER = "FERTILISER", "Fertiliser"
    SEED = "SEED", "Seed"
    PESTICIDE = "PESTICIDE", "Pesticide"
    FEED = "FEED", "Animal feed"
    IRRIGATION = "IRRIGATION", "Irrigation"
    TOOLS = "TOOLS", "Tools"
    OTHER = "OTHER", "Other"


class BulkStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    LOCKED = "LOCKED", "Locked"
    ORDERED = "ORDERED", "Ordered from supplier"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class BulkPurchase(TimeStampedModel):
    """
    A group buy of farm inputs. Suppliers have no accounts: supplier details
    are free text. Joining and confirming are separate steps.
    """

    organiser = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bulk_organised")
    group = models.ForeignKey("groups.FarmerGroup", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="bulk_purchases", help_text="Empty = open to nearby farmers")
    item_name = models.CharField(max_length=120)
    category = models.CharField(max_length=10, choices=BulkCategory.choices, default=BulkCategory.OTHER)
    description = models.TextField(blank=True, max_length=2000)
    unit = models.CharField(max_length=20, help_text="e.g. bag (50 kg), litre")
    unit_price = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    discount_tiers = models.JSONField(default=list, blank=True,
                                      help_text='[{"min_total_quantity": 20, "unit_price": "420.00"}, ...]')
    shared_fees = models.DecimalField(**MONEY, default=0, validators=[MinValueValidator(0)],
                                      help_text="e.g. delivery, split by quantity share")
    supplier_name = models.CharField(max_length=120, blank=True)
    supplier_contact = models.CharField(max_length=200, blank=True)
    deadline = models.DateField()
    status = models.CharField(max_length=10, choices=BulkStatus.choices, default=BulkStatus.OPEN, db_index=True)

    class Meta:
        ordering = ["deadline", "-created_at"]

    def __str__(self):
        return f"{self.item_name} ({self.status})"


class BulkPurchaseMember(TimeStampedModel):
    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PAID = "PAID", "Paid"

    bulk_purchase = models.ForeignKey(BulkPurchase, on_delete=models.CASCADE, related_name="members")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bulk_memberships")
    quantity = models.DecimalField(**QUANTITY, validators=[MinValueValidator(0)])
    calculated_contribution = models.DecimalField(**MONEY, default=0)
    confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    payment_status = models.CharField(max_length=6, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["bulk_purchase", "farmer"], name="unique_bulk_member")]
