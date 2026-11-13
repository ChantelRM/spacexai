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
    core/            shared permissions, pagination, error format, base model, health check
    accounts/        custom User (email login, roles), JWT auth endpoints, seed_dev_data
    locations/       UserLocation, distance utilities, find_nearby_farmers service
    ai/              Grok client, agent loop, tool registry, confirmations, logs
  docs/
    API_CONVENTIONS.md   rules every app must follow
    AI_AGENT.md          how the agent works and how to add a tool
    INTEGRATION_GUIDE.md how Members 2-4 add apps and implement AI services
```

## Endpoints (v1)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health/` | Public |
| POST | `/api/v1/auth/register/` | Public. Returns `user`, `tokens`, `role` |
| POST | `/api/v1/auth/login/` | Public. Email + password. Returns `user`, `tokens`, `role` |
| POST | `/api/v1/auth/refresh/` | Public. Rotates the refresh token |
| POST | `/api/v1/auth/logout/` | Blacklists the refresh token |
| GET, PATCH | `/api/v1/auth/me/` | `role` and `email` cannot change |
| POST | `/api/v1/auth/change-password/` | Revokes old refresh tokens, returns a new pair |
| GET, PUT, PATCH | `/api/v1/locations/me/` | Own location, including coordinates |
| POST | `/api/v1/ai/chat/` | Talk to the assistant (throttled) |
| GET | `/api/v1/ai/conversations/` | Own conversations |
| GET | `/api/v1/ai/conversations/{id}/messages/` | Own messages |
| POST | `/api/v1/ai/actions/{id}/confirm/` | Run a proposed action (owner only, once) |
| POST | `/api/v1/ai/actions/{id}/cancel/` | Discard a proposed action |

See [docs/API_CONVENTIONS.md](docs/API_CONVENTIONS.md) for the error format, pagination and naming rules.
