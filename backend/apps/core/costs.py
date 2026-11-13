"""
Cost allocation shared by bulk purchases, transport and shared services.

Rounding rule (everywhere): every share is rounded to cents, and the
rounding remainder goes to the largest contributor (largest weight; first
one on ties), so the shares always sum exactly to the total.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_cents(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate(total, weights) -> list[Decimal]:
    """
    Split ``total`` in proportion to ``weights``. All-zero weights split equally.

    >>> allocate(Decimal("100"), [1, 1, 1])
    [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')]
    """
    total = to_cents(total)
    weights = [Decimal(w) for w in weights]
    if not weights:
        return []
    if any(w < 0 for w in weights):
        raise ValueError("Weights can't be negative.")
    weight_sum = sum(weights)
    if weight_sum == 0:
        weights = [Decimal("1")] * len(weights)
        weight_sum = Decimal(len(weights))
    shares = [to_cents(total * w / weight_sum) for w in weights]
    remainder = total - sum(shares)
    if remainder:
        largest = max(range(len(weights)), key=lambda i: (weights[i], -i))
        shares[largest] += remainder
    return shares


def percent(part, total) -> float:
    total = Decimal(total)
    return float((Decimal(part) * 100 / total).quantize(CENT)) if total else 0.0


def money_strings(value):
    """Recursively turn Decimals into strings so money keeps its 2 decimal places in JSON."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: money_strings(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [money_strings(v) for v in value]
    return value
