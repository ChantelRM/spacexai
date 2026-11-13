# Farm to Market Co-op

An AI-assisted marketplace and cooperative platform for South African small-scale farmers and wholesale
buyers (restaurants, supermarkets, distributors, processors).

- **Farmers** list produce, receive and manage orders, see which buyers need their produce, and cooperate:
  groups, bulk buying of inputs, shared transport, shared security, insurance information, and equipment
  and storage sharing.
- **Wholesale buyers** search and compare produce, post requirements, get ranked farmer recommendations
  with reasons, place and track orders, and message farmers.
- **The assistant (Grok)** finds and explains matches using approved backend tools only. Anything
  consequential (orders, listings, joining a bulk buy, bookings) needs the user to tap **Confirm**.

| Folder | What |
|---|---|
| [`backend/`](backend/) | Django REST Framework API (SQLite, JWT, OpenAPI). See [backend/README.md](backend/README.md). |
| [`mobile/`](mobile/) | Expo + TypeScript React Native app. See [mobile/README.md](mobile/README.md). |
| [`PROGRESS.md`](PROGRESS.md) | Build checklist, acceptance results and known gaps. |
| [`backend/docs/`](backend/docs/) | API conventions, AI agent, integration guide, decisions, demo script. |

## Quick start (both)

```bash
# 1. API
cd backend
python -m venv .venv && .venv\Scripts\activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # set SECRET_KEY; XAI_API_KEY + XAI_MODEL for the assistant
python manage.py migrate
python manage.py seed_dev_data                    # demo users, password Dev-Passw0rd-2026
python manage.py runserver 0.0.0.0:8000

# 2. App (new terminal)
cd mobile
npm install
cp .env.example .env                              # EXPO_PUBLIC_API_URL, see the comments in the file
npx expo start                                    # press a (Android) / i (iOS) / w (web), or scan with Expo Go
```

Demo logins: `thandi.farmer@example.com` (farmer) and `chef.buyer@example.com` (buyer). See
[backend/docs/DEMO_SCRIPT.md](backend/docs/DEMO_SCRIPT.md) for a 10-minute walkthrough.

## Tests

```bash
cd backend && pytest                      # never calls the real xAI API
cd mobile && npm test && npm run typecheck && npm run lint
```
