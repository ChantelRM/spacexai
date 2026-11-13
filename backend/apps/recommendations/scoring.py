"""
Recommendation scoring shared by buyer→farmer and farmer→buyer matching.

Scores are 0-100. The weights live in ``settings.RECOMMENDATION_WEIGHTS`` so
they can be tuned without code changes:

    quantity 30 · price 20 · distance 20 · timing 10 · quality 10 · reliability 10

Every component returns (points, reasons, gaps) so the result can explain
itself in plain language. Grok only repeats these explanations.
"""
from __future__ import annotations

from decimal import Decimal
from statistics import median

from django.conf import settings
from django.utils import timezone

from apps.listings.models import QUALITY_RANK, QualityGrade, meets_quality
from apps.listings.units import Unit, convert_quantity, format_quantity
from apps.locations.distance import approximate_distance, estimated_km

DEFAULT_WEIGHTS = {"quantity": 30, "price": 20, "distance": 20, "timing": 10, "quality": 10, "reliability": 10}
DISTANCE_ZERO_SCORE_KM = 200  # distance points fall linearly to 0 at this distance
RELIABILITY_MIN_ORDERS = 3


def weights() -> dict:
    return {**DEFAULT_WEIGHTS, **getattr(settings, "RECOMMENDATION_WEIGHTS", {})}


def money(value) -> str:
    return f"R{Decimal(value):,.2f}".replace(",", " ")


def unit_label(unit) -> str:
    return Unit(unit).label if unit in Unit.values else str(unit)


def fmt_date(value) -> str:
    return f"{value.day} {value:%b}"


def price_per(unit_price, from_unit, to_unit) -> Decimal | None:
    """Price per ``to_unit`` given a price per ``from_unit`` (None if not convertible)."""
    per = convert_quantity(Decimal("1"), to_unit, from_unit)  # how many from_units in one to_unit
    return None if per is None else Decimal(unit_price) * per


def score_quantity(available, needed, unit, *, supplier_view=False):
    w = weights()["quantity"]
    if needed <= 0:
        return w, [], []
    coverage = min(Decimal("1"), Decimal(available) / Decimal(needed))
    have, need = format_quantity(available, unit), format_quantity(needed, unit)
    if coverage >= 1:
        reason = (f"You have {have} available, covering the {need} they need" if supplier_view
                  else f"Has {have} available, covering your {need}")
        return w, [reason], []
    gap = (f"Partial supply: you have {have} of the {need} they need" if supplier_view
           else f"Only {have} of your {need}")
    return float(w) * float(coverage), [], [gap]


def score_price(price, unit, median_price=None, max_price=None):
    """``price`` and ``max_price`` per ``unit``; ``median_price`` of the candidates per ``unit``."""
    w = weights()["price"]
    label = f"{money(price)}/{unit_label(unit)}"
    if max_price is not None and price > max_price:
        return 0.0, [], [f"Price {label} is above the maximum {money(max_price)}/{unit_label(unit)}"]
    reasons = []
    points = float(w)
    if median_price:
        rel = float(Decimal(price) / Decimal(median_price))
        points = float(w) * max(0.0, min(1.0, 1.5 - rel))
        if rel < 0.97:
            reasons.append(f"Price {label} is below the median {money(median_price)}/{unit_label(unit)}")
        elif rel <= 1.03:
            reasons.append(f"Price {label} is about the median")
        else:
            reasons.append(f"Price {label} is above the median {money(median_price)}/{unit_label(unit)}")
    if max_price is not None:
        reasons.append(f"Within the maximum price of {money(max_price)}/{unit_label(unit)}")
    return points, reasons, []


def score_distance(origin_loc, other_loc):
    w = weights()["distance"]
    distance = approximate_distance(origin_loc, other_loc)
    km = estimated_km(origin_loc, other_loc)
    if km == float("inf"):
        return 0.0, distance, [], ["Distance unknown (location not set)"]
    points = float(w) * max(0.0, 1 - km / DISTANCE_ZERO_SCORE_KM)
    reason = f"{distance['label']} away" if distance["basis"] == "gps" else distance["label"]
    return points, distance, [reason], []


def score_timing(available_from, needed_by, *, supplier_view=False):
    w = weights()["timing"]
    today = timezone.localdate()
    if available_from is None or available_from <= today:
        return float(w), ["Available now"], []
    if needed_by is None:
        return float(w) * 0.5, [f"Available from {fmt_date(available_from)}"], []
    if available_from <= needed_by:
        return float(w) * 0.7, [f"Available from {fmt_date(available_from)}, before {fmt_date(needed_by)}"], []
    who = "your stock" if supplier_view else "stock"
    return 0.0, [], [f"{who.capitalize()} is only available from {fmt_date(available_from)}, after "
                     f"{fmt_date(needed_by)}"]


def score_quality(grade, min_grade=None):
    w = weights()["quality"]
    label = QualityGrade(grade).label if grade in QualityGrade.values else grade
    if min_grade:
        if meets_quality(grade, min_grade):
            return float(w), [f"{label} meets the minimum {QualityGrade(min_grade).label}"], []
        return 0.0, [], [f"{label} is below the minimum {QualityGrade(min_grade).label}"]
    rank = QUALITY_RANK.get(grade, 1)
    return float(w) * rank / max(QUALITY_RANK.values()), [f"Quality: {label}"], []


def farmer_reliability(farmer) -> dict:
    """completed / (completed + rejected + cancelled by the farmer); neutral below 3 finished orders."""
    from apps.orders.models import Order, OrderStatus

    orders = Order.objects.filter(farmer=farmer)
    completed = orders.filter(status=OrderStatus.COMPLETED).count()
    rejected = orders.filter(status=OrderStatus.REJECTED).count()
    cancelled = orders.filter(status=OrderStatus.CANCELLED, cancelled_by=farmer).count()
    finished = completed + rejected + cancelled
    return {"completed": completed, "finished": finished,
            "ratio": (completed / finished) if finished >= RELIABILITY_MIN_ORDERS else None}


def score_reliability(stats):
    w = weights()["reliability"]
    if stats["ratio"] is None:
        return float(w) * 0.5, ["New on the platform: not enough orders yet to rate reliability"], []
    return float(w) * stats["ratio"], [f"Completed {stats['completed']} of {stats['finished']} orders"], []


def median_or_none(values):
    values = [v for v in values if v is not None]
    return Decimal(str(median(values))) if values else None
