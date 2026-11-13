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
- [x] Seed data for Parts 2-3 (see Part 4)

## Part 4: Cooperative (Member 4)
- [x] `apps.core.costs.allocate`: shared cents rounding (remainder to the largest contributor)
- [x] groups: create/search (nearest first)/join (open or request)/invite/accept/decline/leave/remove/promote, posts and admin-only announcements, last-admin protection
- [x] bulk: purchases with discount tiers + shared fees, pure `calculate_cost_shares` (worked example 5/8/7/10 tested), recalculation on join/leave/terms (resets changed confirmations), separate confirm, lock only when all confirmed, calculator endpoint
- [x] transport: requests and participants, WEIGHT/VOLUME/SPACE/EQUAL/DISTANCE/AGREED splits, AGREED sum validation, capacity → FULL, confirm flow, ranked matching
- [x] services: shared security costs (EQUAL/AGREED), security alerts (area/group scoped, ID/phone numbers rejected), insurance products + quote requests, disclaimer on every insurance response
- [x] equipment: listings incl. storage capacity, bookings with cost estimates, no overlapping APPROVED equipment bookings, storage capacity limit, owner approve/decline
- [x] AI: `find_bulk_purchases`, `calculate_cost_shares`, `find_transport_requests`, `find_farmer_groups`, `find_equipment` wired; `join_bulk_purchase`, `confirm_bulk_purchase_contribution`, `join_transport_request`, `request_equipment_booking` added with confirmation; `find_nearby_farmers` gained a produce filter
- [x] Buyers get 403 on every cooperative endpoint (tested)
- [x] `seed_dev_data`: 8 farmers + 5 buyers (4 provinces, mixed GPS), profiles, 12 listings, 7 requirements, orders in 5 states, a conversation, 2 groups, a fertiliser bulk buy, a shared trip, 3 equipment/storage items, a security patrol + alert, demo insurance info
- Status at end of Part 4: 254 backend tests pass; `check`, `makemigrations --check` and the strict schema check are clean.

## Part 5: Mobile app (Member 5)
- [ ] Expo + TypeScript app in `mobile/`

## Part 6: Integration and handover
- [ ] End-to-end scenarios · [ ] acceptance criteria · [ ] docs and demo script

## Notes
- Tool summaries may take `(data, user)`; the registry also turns lookup errors raised inside tool input validation (e.g. NotFound) into a logged `invalid` tool result instead of failing the chat request.
- Concurrency: accepting an order uses `select_for_update` plus a conditional `UPDATE ... WHERE quantity_available >= qty`, so two accepts can never oversell even on SQLite (where row locks are a no-op). Tested by simulating the competing write; true multi-threaded tests are not run on SQLite.
- AI order summaries show prices at proposal time; the order is created at confirmation with current prices. The order stays PENDING until the farmer accepts, so the buyer can still cancel.
- Pillow installs from a downloaded wheel: `pip install Pillow` intermittently failed to resolve on this machine.
