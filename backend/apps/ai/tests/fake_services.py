"""Fake feature services used to test the confirmation flow end to end."""

CALLS = []


def create_or_update_listing(user, *, produce, quantity, unit, price_per_unit, listing_id=None,
                             available_from=None, available_until=None, notes=""):
    CALLS.append({"user_id": user.pk, "produce": produce, "quantity": quantity})
    return {
        "available": True,
        "listing_id": 101,
        "created": listing_id is None,
        "produce": produce,
        "quantity": float(quantity),
        "unit": unit,
        "price_per_unit": float(price_per_unit),
        "available_from": available_from.isoformat() if available_from else None,
        "available_until": available_until.isoformat() if available_until else None,
    }
