"""
Pure bulk-purchase cost calculation. No database access; heavily unit-tested.

    total quantity -> applicable discount tier -> unit price
    goods total    = total quantity × unit price
    grand total    = goods total + shared fees
    member share   = grand total × (member quantity ÷ total quantity)
                     (= quantity × unit price + their quantity-share of the fees)

Shares are rounded to cents and the rounding remainder goes to the largest
contributor, so they sum exactly to the grand total (apps.core.costs).
"""
from __future__ import annotations

from decimal import Decimal

from apps.core.costs import allocate, percent, to_cents


def applicable_tier(total_quantity, discount_tiers) -> dict | None:
    """The tier with the highest min_total_quantity that the total reaches, or None."""
    best = None
    for tier in discount_tiers or []:
        if Decimal(str(tier["min_total_quantity"])) <= total_quantity:
            if best is None or Decimal(str(tier["min_total_quantity"])) > Decimal(str(best["min_total_quantity"])):
                best = tier
    return best


def validate_tiers(discount_tiers) -> list[dict]:
    cleaned = []
    for tier in discount_tiers or []:
        try:
            min_q = Decimal(str(tier["min_total_quantity"]))
            price = Decimal(str(tier["unit_price"]))
        except Exception:
            raise ValueError("Each tier needs min_total_quantity and unit_price numbers.")
        if min_q <= 0 or price < 0:
            raise ValueError("Tier quantities must be positive and prices not negative.")
        cleaned.append({"min_total_quantity": str(min_q), "unit_price": str(to_cents(price))})
    if len({t["min_total_quantity"] for t in cleaned}) != len(cleaned):
        raise ValueError("Two tiers have the same minimum quantity.")
    return sorted(cleaned, key=lambda t: Decimal(t["min_total_quantity"]))


def calculate_cost_shares(lines: list[dict], unit_price, discount_tiers=None, shared_fees=0,
                          method="quantity") -> dict:
    """
    ``lines``: [{"label": "Thandi", "quantity": 5}, ...].
    ``method``: "quantity" (default) or "equal".
    """
    if not lines:
        raise ValueError("Add at least one participant.")
    quantities = [Decimal(str(line.get("quantity") or 0)) for line in lines]
    if any(q < 0 for q in quantities):
        raise ValueError("Quantities can't be negative.")
    total_quantity = sum(quantities)
    base_price = to_cents(unit_price)
    tier = applicable_tier(total_quantity, discount_tiers)
    price = to_cents(tier["unit_price"]) if tier else base_price
    goods_total = to_cents(total_quantity * price)
    fees = to_cents(shared_fees or 0)
    grand_total = goods_total + fees
    weights = quantities if method == "quantity" else [Decimal("1")] * len(lines)
    shares = allocate(grand_total, weights)
    fee_shares = allocate(fees, weights) if fees else [Decimal("0.00")] * len(lines)
    return {
        "method": method,
        "total_quantity": total_quantity,
        "base_unit_price": base_price,
        "unit_price": price,
        "applied_tier": tier,
        "goods_total": goods_total,
        "shared_fees": fees,
        "total": grand_total,
        "savings": to_cents(total_quantity * base_price) - goods_total,
        "shares": [
            {
                "label": line.get("label", ""),
                "quantity": q,
                "fee_amount": fee,
                "share_amount": share,
                "share_percent": percent(share, grand_total),
            }
            for line, q, share, fee in zip(lines, quantities, shares, fee_shares)
        ],
    }


def split_total(total_cost, participants: list[dict], split_method="by_quantity") -> dict:
    """Ad hoc split of a known total (transport, equipment hire). AI contract: CostShareResult."""
    total = to_cents(total_cost)
    if split_method == "by_quantity":
        weights = [Decimal(str(p.get("quantity") or 0)) for p in participants]
    else:
        weights = [Decimal("1")] * len(participants)
    shares = allocate(total, weights)
    return {
        "available": True,
        "total_cost": float(total),
        "split_method": split_method,
        "shares": [{"label": p.get("label", ""), "quantity": float(p["quantity"]) if p.get("quantity") is not None
                    else None, "share_amount": float(s), "share_percent": percent(s, total)}
                   for p, s in zip(participants, shares)],
    }
