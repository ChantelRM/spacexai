from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.listings.models import MONEY, QUANTITY
from apps.listings.units import Unit


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    DISPATCHED = "DISPATCHED", "Dispatched"
    DELIVERED = "DELIVERED", "Delivered"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PAID = "PAID", "Paid"
    DISPUTED = "DISPUTED", "Disputed"


class Order(TimeStampedModel):
    """
    An order from one buyer to one farmer. Status changes only through
    apps.orders.services (the state machine). Payment is settled outside the
    platform; payment_status is tracked manually.
    """

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders_placed")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders_received")
    status = models.CharField(max_length=10, choices=OrderStatus.choices, default=OrderStatus.PENDING, db_index=True)
    payment_status = models.CharField(max_length=8, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    delivery_date = models.DateField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True, max_length=1000)
    total_amount = models.DecimalField(**MONEY, default=0)
    rejection_reason = models.TextField(blank=True, max_length=500)
    cancellation_reason = models.TextField(blank=True, max_length=500)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    buyer_requirement = models.ForeignKey("buyers.BuyerRequirement", on_delete=models.SET_NULL, null=True,
                                          blank=True, related_name="orders")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    listing = models.ForeignKey("listings.ProduceListing", on_delete=models.PROTECT, related_name="order_items")
    # Snapshot at order time:
    produce_name = models.CharField(max_length=80)
    unit = models.CharField(max_length=8, choices=Unit.choices)
    price_per_unit = models.DecimalField(**MONEY)
    quantity = models.DecimalField(**QUANTITY)
    line_total = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="orderitem_quantity_gt_0")]

    def __str__(self):
        return f"{self.quantity} {self.unit} {self.produce_name}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=10, choices=OrderStatus.choices, blank=True)
    to_status = models.CharField(max_length=10, choices=OrderStatus.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "order status history"
