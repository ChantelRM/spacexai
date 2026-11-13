# API conventions

Every app in this backend follows these rules, so the mobile app sees one consistent API. If something here doesn't fit your feature, raise it with the team before doing something different.

## URLs

- Everything lives under `/api/v1/<app>/...`, e.g. `/api/v1/listings/`, `/api/v1/orders/{id}/`.
- Use plural nouns for collections (`/listings/`, `/orders/`) and IDs for single items (`/listings/42/`).
- Use a sub-path for actions that aren't plain CRUD: `POST /api/v1/orders/42/cancel/`.
- `me/` means "the current user's own record": `/auth/me/`, `/locations/me/`.
- Always use a trailing slash.
- Register your app's URLs in `config/urls.py` inside the `api_v1` list:
  `path("listings/", include("apps.listings.urls")),`

## JSON

- `snake_case` field names.
- Datetimes are ISO-8601 with an offset, e.g. `2026-11-13T09:30:00+02:00`. The server time zone is `Africa/Johannesburg`, and datetimes are stored in UTC (`USE_TZ = True`).
- Dates are `YYYY-MM-DD`.
- Money is in South African rand (ZAR). Send it as a decimal string or number with 2 decimal places, and name the field after what it is: `price_per_unit`, `total_cost`.
- Enum values are UPPER_SNAKE strings that match Django `TextChoices` values, e.g. `"FARMER"`, `"GAUTENG"`. Add a `*_display` read-only field if the app needs a label.
- Never return another user's email, phone number, exact coordinates or street address. For locations, use `apps.locations.serializers.public_location()`.

## Authentication

- JWT bearer tokens: `Authorization: Bearer <access>`.
- Access tokens last 15 minutes and refresh tokens 14 days. Refresh rotates: each `POST /auth/refresh/` returns a new refresh token and blacklists the old one.
- Both tokens carry a `role` claim (`FARMER` or `WHOLESALE_BUYER`). The app can read it for UI decisions, but the server always checks the role from the database.
- Everything requires authentication by default (`IsAuthenticated`). Only make an endpoint public on purpose (`permission_classes = [AllowAny]`).

## Permissions (`apps/core/permissions.py`)

| Class | Use |
|---|---|
| `IsFarmer` | Farmers only |
| `IsWholesaleBuyer` | Wholesale buyers only |
| `role_required("FARMER", "WHOLESALE_BUYER")` | Builds a class for any set of roles |
| `IsOwnerOrReadOnly` | Object-level: anyone authenticated reads; only the owner writes |
| `IsOwner` | Object-level: only the owner reads or writes |

Owner checks look at `obj.user` by default. Set `owner_field` on the view if your FK has another name, e.g. `owner_field = "farmer"` or `owner_field = "order__buyer"`.

```python
from apps.core.permissions import IsFarmer, IsOwnerOrReadOnly

class ListingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    owner_field = "farmer"

    def get_permissions(self):
        if self.action == "create":
            return [IsFarmer()]
        return super().get_permissions()
```

Always scope querysets to what the user may see (`.filter(user=request.user)` and so on). A permission class alone does not hide rows from list endpoints.

## Errors

Every error response has the same shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable summary",
    "details": {"quantity": ["Ensure this value is greater than or equal to 0.01."]}
  }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `validation_error` | Serializer or field errors. `details` maps field to a list of messages. Non-field errors go under `non_field_errors`. |
| 400 | `parse_error` | Malformed JSON |
| 401 | `not_authenticated` | No token |
| 401 | `authentication_failed`, `token_not_valid` | Bad credentials or token |
| 403 | `permission_denied` | Wrong role or not the owner |
| 404 | `not_found` | Missing, or not visible to this user |
| 405 | `method_not_allowed` | |
| 409 | e.g. `action_not_pending` | State conflicts |
| 410 | e.g. `action_expired` | The resource has expired |
| 429 | `throttled` | `details.retry_after_seconds` says when to retry |
| 500 | `server_error` | Unexpected; details are only in server logs |
| 503 | `ai_service_unavailable` | Grok unavailable |

The format comes from `apps.core.exceptions.api_exception_handler`, so just raise normal DRF exceptions (`ValidationError`, `PermissionDenied`, `NotFound`) or your own `APIException` subclass with `status_code` and `default_code`. Don't build error JSON by hand.

`message` is safe to show to users. Never put exception text, SQL or secrets in it.

## Pagination

List endpoints use page-number pagination: default 20 per page, maximum 100.

```
GET /api/v1/ai/conversations/?page=2&page_size=50
{"count": 134, "next": "...?page=3&page_size=50", "previous": "...?page=1&page_size=50", "results": [...]}
```

`ListAPIView` and `ViewSet` lists get this automatically. In a plain `APIView`, use `apps.core.pagination.StandardPagination` yourself.

## Throttling

| Scope | Rate | Applies to |
|---|---|---|
| `anon` | 60/min | Unauthenticated requests |
| `user` | 600/min | Authenticated requests |
| `auth` | 10/min | Register, login and change-password |
| `ai_chat` | 20/min | `POST /ai/chat/` |

To add a scope, add it to `DEFAULT_THROTTLE_RATES` in `config/settings/base.py` and set `throttle_classes = [UserRateThrottle, ScopedRateThrottle]` and `throttle_scope = "..."` on the view. Throttle counters use Django's cache (local memory for now), so they are per process. Use a shared cache such as Redis in production.

## Models

- Inherit from `apps.core.models.TimeStampedModel` to get `created_at` and `updated_at`.
- Link users with `models.ForeignKey(settings.AUTH_USER_MODEL, ...)`. Never import `User` in models, and never copy user fields into your own models.
- Use only portable ORM features: no raw SQL and no SQLite-only behaviour. We will move to PostgreSQL.
- Commit migrations. Run `python manage.py makemigrations --check` before pushing.

## OpenAPI

The schema at `/api/schema/` (Swagger UI at `/api/docs/`) is the contract the mobile app builds against. Keep it accurate:

- Use serializers for requests and responses, or `@extend_schema(request=..., responses=...)` on `APIView` methods.
- Run `python manage.py spectacular --validate --fail-on-warn --file schema.yml` before pushing. It must pass with no warnings.
