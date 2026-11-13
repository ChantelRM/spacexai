# Build progress

Source brief: `full_build_agent_prompt.md`. Decisions: `backend/docs/DECISIONS.md`.

Legend: [x] done · [~] in progress · [ ] not started · [!] blocked

## Part 1: Foundation and AI agent (Member 1)
- [x] Settings (base/dev/test) from the environment, `.env.example`, `.env` git-ignored
- [x] Email-login `User` with `FARMER`/`WHOLESALE_BUYER`, role immutable through the API
- [x] JWT register/login/refresh/logout/me/change-password
- [x] `core`: permissions, `TimeStampedModel`, pagination, error format, throttling, health, OpenAPI + Swagger
- [x] `locations`: `UserLocation`, haversine, fallback tiers, `proximity_rank`, `/locations/me/`
- [x] `ai`: models, Grok client (Responses API, retry, 503), registry, confirmation flow, chat + history endpoints
- [x] `find_nearby_farmers`; other tools registered as stubs
- [x] `seed_dev_data`; admin registration; README and docs
- Audit (start of the full build): 132 tests pass, `check` and `makemigrations --check` are clean, and the OpenAPI schema validates with no warnings.

## Part 2: Farmers and listings (Member 2)
- [x] `farmers`: `FarmerProfile` (admin-only `is_verified`), `/farmers/me/profile/`, public `/farmers/{id}/`
- [x] `listings`: categories (seeded), listings, images (≤5, ≤5 MB, JPEG/PNG/WebP), units, pause/resume/soft delete
- [x] `create_or_update_listing` AI tool wired to `apps.listings.services` (confirmation required)
- [x] `search_buyer_requirements` (in `apps/recommendations/services.py`, shared scoring) + `/farmers/me/recommended-buyers/`; AI stub replaced

## Part 3: Buyers, recommendations, orders, messaging (Member 3)
- [x] `core.Notification` + `/notifications/` (list, unread count, read, read-all)
- [x] `buyers`: profile, requirements CRUD (DELETE closes), public buyer profile
- [x] `recommendations`: `scoring.py` (weights in `settings.RECOMMENDATION_WEIGHTS`), both directions, multi-item + `covers_multiple`, `RecommendationLog`, `/recommendations/farmers/`, `/buyers/me/recommended-farmers/`
- [x] `orders`: state machine in `services.py`, stock reserve/restore with conditional UPDATE, history, notifications, payment status, single-farmer orders
- [x] `marketplace`: search (all filters, sorts, pagination), detail, compare, farmer discovery
- [x] `messaging`: buyer↔farmer conversations, participants only, unread counts
- [x] AI tools: `search_recommended_farmers`, `search_buyer_requirements` wired; `compare_listings`, `get_my_orders` added; `create_order`, `respond_to_order` added with confirmation
- [ ] Seed data for Parts 2-3 (planned together with Part 4 seed data)

## Part 4: Cooperative (Member 4)
- [ ] groups · [ ] bulk purchasing · [ ] transport · [ ] security/insurance services · [ ] equipment/storage
- [ ] AI tools wired, plus the commitment tools with confirmation

## Part 5: Mobile app (Member 5)
- [ ] Expo + TypeScript app in `mobile/`

## Part 6: Integration and handover
- [ ] End-to-end scenarios · [ ] acceptance criteria · [ ] docs and demo script

## Notes
- Concurrency: accepting an order uses `select_for_update` plus a conditional `UPDATE ... WHERE quantity_available >= qty`, so two accepts can never oversell even on SQLite (where row locks are a no-op). Tested by simulating the competing write; true multi-threaded tests are not run on SQLite.
- AI order summaries show prices at proposal time; the order is created at confirmation with current prices. The order stays PENDING until the farmer accepts, so the buyer can still cancel.
- Pillow installs from a downloaded wheel: `pip install Pillow` intermittently failed to resolve on this machine.
