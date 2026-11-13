# Farmer Cooperative Marketplace: Backend

Django REST Framework API for the marketplace that connects small-scale farmers with wholesale buyers, plus the Grok AI assistant.

- **Account types:** `FARMER` and `WHOLESALE_BUYER` only.
- **Auth:** JWT (access + refresh with rotation), email login.
- **Database:** SQLite for now. The code uses only portable ORM features, so it can move to PostgreSQL later.
- **AI:** Grok through the xAI API. The API key stays on the server. Grok can only call the approved backend tools.

## Quick start

Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # then edit .env (see below)
python manage.py migrate
python manage.py createsuperuser  # asks for email, display name and role
python manage.py seed_dev_data    # optional: 7 farmers + 3 buyers, password Dev-Passw0rd-2026
python manage.py runserver
```

Then open:

| URL | What |
|---|---|
| http://127.0.0.1:8000/api/docs/ | Swagger UI (the API contract) |
| http://127.0.0.1:8000/api/schema/ | OpenAPI 3 schema (YAML; add `?format=json` for JSON) |
| http://127.0.0.1:8000/api/v1/health/ | Health check |
| http://127.0.0.1:8000/admin/ | Django admin |

From an Android emulator, the host machine is `10.0.2.2` (already in the default `ALLOWED_HOSTS`).

### Environment variables (`.env`)

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | yes | Long random string. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |
| `DEBUG` | no | `True` for local development. |
| `ALLOWED_HOSTS` | no | Comma-separated. |
| `CORS_ALLOWED_ORIGINS` | no | Comma-separated origins (e.g. the Expo web dev server). |
| `DATABASE_URL` | no | Defaults to `sqlite:///backend/db.sqlite3`. |
| `XAI_API_KEY` | for AI | Server-side only. Never put it in the mobile app. |
| `XAI_MODEL` | for AI | A current Grok model name from https://docs.x.ai. Deliberately not hard-coded. |
| `XAI_BASE_URL` | no | Default `https://api.x.ai/v1`. |
| `XAI_TIMEOUT_SECONDS`, `XAI_MAX_RETRIES` | no | Defaults 30 s and 2 retries. |

Without `XAI_API_KEY` and `XAI_MODEL`, everything works except `POST /api/v1/ai/chat/`, which returns `503 ai_service_unavailable`.

Settings modules: `config.settings.dev` (default for `manage.py`), `config.settings.test` (pytest). Add a `prod.py` when we deploy.

## Tests

```bash
cd backend
pytest                 # full suite; never calls the real xAI API
pytest apps/ai -q      # one app
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file schema.yml
```

All Grok calls are mocked. A global fixture also blocks the real SDK client, so a test that forgets to mock fails instead of calling xAI.

## Layout

```
backend/
  config/            settings (base/dev/test), urls, wsgi, asgi
  apps/
    core/            permissions, pagination, error format, notifications, cost allocation, health
    accounts/        custom User (email login, roles), JWT auth, seed_dev_data
    locations/       UserLocation, distance utilities, find_nearby_farmers
    ai/              Grok client, agent loop, tool registry, confirmations, audit log
    farmers/         farm profiles, public farmer profile
    listings/        produce listings, categories, images, units
    buyers/          buyer profiles, requirements
    recommendations/ scoring engine (both directions), recommendation log
    orders/          order state machine, stock reservation, history
    messaging/       buyer-farmer conversations
    marketplace/     search, compare, farmer discovery
    groups/ bulk/ transport/ services/ equipment/   cooperative features (farmers only)
  docs/              API_CONVENTIONS, AI_AGENT, INTEGRATION_GUIDE, DECISIONS, DEMO_SCRIPT
```

## Endpoints

Everything is under `/api/v1/`, and the full, always-current list is in Swagger at `/api/docs/`. Main
groups:

| Prefix | What |
|---|---|
| `auth/` | register, login, refresh, logout, me, change-password |
| `locations/me/` | your location (only you see your coordinates) |
| `farmers/` | `me/profile/`, `me/recommended-buyers/`, public `{id}/` |
| `listings/` | `categories/`, `mine/` CRUD + `pause/`, `resume/`, `images/` |
| `buyers/` | `me/profile/`, `requirements/`, `me/recommended-farmers/`, public `{id}/` |
| `recommendations/farmers/` | ad hoc ranked farmers (multi-item) |
| `marketplace/` | `listings/` search, `compare/`, `farmers/` discovery |
| `orders/` | list/create, `accept`, `reject`, `dispatch`, `confirm-receipt`, `complete`, `cancel`, `payment-status` |
| `messaging/conversations/` | threads and messages |
| `notifications/` | list, unread count, read, read-all |
| `ai/` | `chat/`, `conversations/`, `actions/{id}/confirm/` and `cancel/` |
| `groups/`, `bulk-purchases/`, `transport/`, `services/`, `equipment/` | cooperative features (farmers only) |

See [docs/API_CONVENTIONS.md](docs/API_CONVENTIONS.md) for the error format, pagination and naming rules,
and [docs/DECISIONS.md](docs/DECISIONS.md) for product defaults (no in-app payments, farmer must accept
orders, and so on).
