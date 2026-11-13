"""
Safety net applied to every tool result before it reaches Grok or the app.
Services must already avoid these fields; this catches mistakes.
"""
from collections.abc import Mapping

PRIVATE_KEYS = frozenset({
    "latitude", "longitude", "lat", "lng", "lon", "coordinates", "coords", "location_point",
    "email", "email_address", "phone", "phone_number", "mobile", "address_line", "street_address",
    "password",
})


def scrub_private_fields(value):
    """Recursively drop private keys from dicts inside the value."""
    if isinstance(value, Mapping):
        return {k: scrub_private_fields(v) for k, v in value.items() if str(k).lower() not in PRIVATE_KEYS}
    if isinstance(value, (list, tuple)):
        return [scrub_private_fields(v) for v in value]
    return value
