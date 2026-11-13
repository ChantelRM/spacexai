# Integration guide for Members 2-5

This guide explains how to build your part on top of the foundation. Read [API_CONVENTIONS.md](API_CONVENTIONS.md) first.

## Who owns what

| Member | Owns | Suggested app(s) | Must NOT create |
|---|---|---|---|
| 1 | Project setup, `accounts`, `core`, `locations`, `ai` | (done) | |
| 2 | `FarmerProfile`, `ProduceListing` | `apps/listings` | User or location fields |
| 3 | `WholesaleBuyerProfile`, `BuyerRequirement`, `Order`, `OrderItem`, `Conversation`, `Message` | `apps/buyers` (plus `apps/orders` and `apps/messaging` if you prefer) | |
| 4 | `FarmerGroup`, `BulkPurchase`, `TransportRequest`, `EquipmentListing`, ... | `apps/cooperation` | |
| 5 | React Native app | (frontend) | |

The suggested app names match the default AI service paths in `apps/ai/services_contract.py`. If you choose another name, update `SERVICE_PROVIDERS` there (or set `AI_SERVICE_PROVIDERS` in settings).

## Adding an app

```bash
cd backend
mkdir apps/listings
python manage.py startapp listings apps/listings
```

1. In `apps/listings/apps.py` set `name = "apps.listings"` and `label = "listings"`.
2. Add `"apps.listings"` to `INSTALLED_APPS` in `config/settings/base.py`.
3. Add `path("listings/", include("apps.listings.urls"))` to the `api_v1` list in `config/urls.py`.
4. Put tests in `apps/listings/tests/test_*.py`. Shared fixtures from `backend/conftest.py` are available everywhere: `api_client`, `farmer`, `buyer`, `farmer_client`, `buyer_client` and `auth_client(user)`.
5. Run `python manage.py makemigrations listings`, `pytest`, and the schema check before pushing.

## Linking to users and locations

**Never duplicate user or location data.**

```python
from django.conf import settings
from apps.core.models import TimeStampedModel

class FarmerProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="farmer_profile")
    farm_name = models.CharField(max_length=120)
    # no email, phone, province, town or coordinates here: they live on User and UserLocation

class ProduceListing(TimeStampedModel):
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="produce_listings",
                               limit_choices_to={"role": "FARMER"})
```

- **Role:** check `user.role == Role.FARMER` (`from apps.accounts.models import Role`), or use `user.is_farmer` / `user.is_wholesale_buyer`. In views, use the permission classes in `apps.core.permissions`. `limit_choices_to` only affects forms and admin, so also validate the role in your serializer or service.
- **Location:** `user.location` is a `UserLocation`, and it may not exist. Catch `UserLocation.DoesNotExist`, or use `UserLocation.objects.filter(user=user).first()`.
- **Showing someone's location:** always use `public_location(their_location, viewer_location)` from `apps.locations.serializers`. It returns province, municipality, town and an approximate distance, never coordinates or the address. `PublicLocationSerializer` documents the shape for OpenAPI.
- **Nearest first:** `sorted(items, key=lambda x: proximity_rank(me_loc, x.farmer.location))` from `apps.locations.distance`. It works with or without GPS. Use `within_km(a, b, max_km)` for distance filters and `approximate_distance(a, b)` for display.
- **Tests:** use `FarmerFactory`, `BuyerFactory` (`apps.accounts.factories`) and `UserLocationFactory` (`apps.locations.factories`).

## Implementing an AI service

The AI assistant already has tools registered for your features. Until your service exists, each one tells users *"This feature is not implemented yet."* To make a tool work:

1. Open `apps/ai/services_contract.py` and find your tool's `Protocol` (signature) and `TypedDict` (return shape), plus its path in `SERVICE_PROVIDERS`:

| Tool | Path | Roles | Confirmation |
|---|---|---|---|
| `search_buyer_requirements` | `apps.listings.ai_services` | farmer | no |
| `create_or_update_listing` | `apps.listings.ai_services` | farmer | **yes** |
| `search_recommended_farmers` | `apps.buyers.ai_services` | buyer | no |
| `find_bulk_purchases` | `apps.cooperation.ai_services` | farmer | no |
| `calculate_cost_shares` | `apps.cooperation.ai_services` | farmer | no |
| `find_transport_requests` | `apps.cooperation.ai_services` | farmer | no |
| `find_farmer_groups` | `apps.cooperation.ai_services` | farmer | no |
| `find_equipment` | `apps.cooperation.ai_services` | farmer | no |

2. Create the module with a function of exactly that name and signature. Arguments arrive **already validated** by the tool's input serializer (`apps/ai/tools/definitions.py`), as keyword arguments. Dates are `datetime.date` and money and quantities are `Decimal`.

```python
# apps/buyers/ai_services.py
from apps.locations.distance import proximity_rank, within_km
from apps.locations.serializers import public_location


def search_recommended_farmers(user, *, produce, quantity, unit, max_distance_km=None,
                               needed_by=None, limit=10):
    buyer_loc = getattr(user, "location", None)
    listings = (ProduceListing.objects.select_related("farmer__location")
                .filter(produce__icontains=produce, unit=unit, is_active=True))
    matches = []
    for listing in listings:
        farmer_loc = getattr(listing.farmer, "location", None)
        if not within_km(buyer_loc, farmer_loc, max_distance_km):
            continue
        reasons = [f"Has {produce} listed"]
        shortfall = None
        if listing.quantity >= quantity:
            reasons.append("Enough stock for your order")
        else:
            shortfall = f"Has {listing.quantity} {unit} of the {quantity} {unit} you need"
        matches.append((proximity_rank(buyer_loc, farmer_loc), {
            "farmer_id": listing.farmer_id,
            "farmer_display_name": listing.farmer.display_name,
            "listing_id": listing.id,
            "produce": listing.produce,
            "available_quantity": float(listing.quantity),
            "unit": listing.unit,
            "price_per_unit": float(listing.price_per_unit),
            "available_from": listing.available_from.isoformat() if listing.available_from else None,
            "location": public_location(farmer_loc, buyer_loc),
            "match_reasons": reasons,
            "shortfall": shortfall,
        }))
    matches.sort(key=lambda m: m[0])
    results = [m[1] for m in matches[:limit]]
    return {"available": True, "count": len(results), "results": results}
```

3. That's all. The registry finds the function automatically, and the tool stops returning "not available". There is no registration step, and you don't need to edit `apps/ai`.

Rules for services:

- **Run as `user`.** Only return what that user may see. In write services such as `create_or_update_listing`, check that `listing_id` belongs to `user` and raise `rest_framework.exceptions.PermissionDenied` if it doesn't.
- **Return plain JSON types** in the documented shape, with dates as ISO strings and Decimals as floats.
- **No contact details or coordinates** for other users. The registry strips known keys as a safety net, but don't rely on it.
- **Do the matching and ranking in the service.** Grok only explains it, so return `match_reasons` and `shortfall`.
- **Raise `ValidationError`** for business-rule failures (for example "available_until is in the past"). The registry reports it to Grok and logs it.
- **Write services never commit anything themselves.** `create_or_update_listing` only runs after the user confirms. Read-only services must not change data.
- **A broken import inside your module raises an error.** It is not hidden as "not implemented".

Test your service directly, then through the tool:

```python
from apps.ai.tools.registry import execute_tool_call

outcome = execute_tool_call(buyer, "search_recommended_farmers",
                            '{"produce": "potatoes", "quantity": 500, "unit": "kg"}')
assert outcome.status == "success"
```

### Changing a tool's inputs

If your service needs a different input (a new filter, say), update both the input serializer in `apps/ai/tools/definitions.py` and the `Protocol` in `services_contract.py` in the same PR, and tell Member 1. Keep descriptions short and factual, because Grok reads them.

### Adding a new consequential action

For actions such as placing an order, committing to a bulk purchase or making a payment, register a new tool with `requires_confirmation=True` and a `summarize(data)` that states exactly what will happen, including amounts and dates. Never add a tool that confirms, pays or commits directly. See [AI_AGENT.md](AI_AGENT.md#adding-a-new-tool).

### Replacing a tool completely

This should be rare. Use `register_tool(..., replace=True)` in your app's `AppConfig.ready()`, and talk to Member 1 first.

## For Member 5 (mobile app)

- The contract is `/api/docs/` (or `/api/schema/?format=json` for code generation).
- Store the refresh token securely (e.g. `expo-secure-store`). On 401 `token_not_valid`, call `/auth/refresh/` once, then send the user to login. Save the **new** refresh token after every refresh, because tokens rotate.
- Show `error.message` to users and map `error.details` to form fields.
- For the AI chat, render `reply` as text, `data.<tool_name>.results` as cards, and `pending_action` as a confirmation card that calls `/ai/actions/{id}/confirm/` or `/cancel/`. Handle 410 (expired) by telling the user to ask again.
- `latitude` and `longitude` are only ever present on `/locations/me/`, for the user's own location.
