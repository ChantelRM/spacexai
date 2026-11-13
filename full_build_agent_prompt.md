# Task: Complete the agricultural cooperative marketplace (all five team areas)

You are continuing work on an existing repository for an AI-powered agricultural marketplace and cooperative platform. A backend foundation may already exist (Member 1's work: Django REST Framework, custom user, roles, auth, shared conventions, locations, Grok AI agent). Your job:

1. **Audit and finish Member 1's work** wherever it is missing or incomplete.
2. **Build Members 2, 3 and 4's backend modules** (farmer marketplace, buyer marketplace and orders, cooperative features).
3. **Build Member 5's React Native mobile app** and connect it to the API.
4. **Wire every AI tool** to real service logic, replacing the stubs.

This is a large job. Work in the order of the parts below. Make small, tested, committed steps, and keep a running `PROGRESS.md` at the repo root (see §0.3) so that work can resume cleanly in a new session if you run out of context.

---

## 0. Before you write any code

### 0.1 Read the repository
- Read `README.md` and everything in `docs/` (especially `API_CONVENTIONS.md`, `AI_AGENT.md`, `INTEGRATION_GUIDE.md`), `apps/ai/services_contract.py`, the settings, and every existing app.
- Run the existing test suite and `python manage.py check` and `makemigrations --check`. Note anything failing.
- **Follow existing conventions.** Where the existing code and this prompt disagree on a detail, the existing code wins, unless it breaks a rule in §0.2. In that case fix it and note why in `PROGRESS.md`.

### 0.2 Non-negotiable rules (apply to every part)
- Exactly **two account types**: `FARMER` and `WHOLESALE_BUYER`. No supplier, transport, insurance or security accounts.
- **One** `User` model and **one** `UserLocation` model. Never create duplicate user, profile or location models. Profiles link to `User` one-to-one.
- **SQLite via the Django ORM only**: nothing database-specific, so we can move to PostgreSQL later. Wrap multi-step writes in `transaction.atomic()`.
- Use the shared `core` permissions, pagination, `TimeStampedModel`, error format and `/api/v1/` URL conventions.
- Money is `DecimalField(max_digits=12, decimal_places=2)` in **ZAR**. Never use floats for money or quantities.
- **Location privacy:** another user's exact latitude and longitude are never returned anywhere, including AI tool results. Show town, municipality and province plus an approximate distance (from the `locations` distance utility).
- **Grok never accesses the database.** It only calls registered tools. The backend does all filtering, matching, ranking and calculating. Grok explains the results.
- Grok must **never invent** farmers, buyers, prices or stock, and **never commit a user** to an order, purchase, payment or booking. Every consequential action goes through the existing `PendingAction` confirmation flow.
- The xAI API key stays server-side only. It never goes in the mobile app.
- Tests must never call the real xAI API (mock it).
- Every new endpoint appears correctly in the OpenAPI schema (`/api/docs/`). Use `drf-spectacular` annotations where the schema would otherwise be wrong.

### 0.3 Progress tracking
Create or maintain `PROGRESS.md` with a checklist of every part and sub-part below, marked done, in progress or blocked, plus notes on assumptions and decisions. Update it and commit at the end of each part. If you have to stop partway, leave it accurate so the next session can continue.

### 0.4 Product decisions to use (defaults, record them in `docs/DECISIONS.md`)
The team hasn't finalised these yet. Implement the defaults below and keep each one easy to change:
| Decision | Default to implement |
|---|---|
| Payments | **No in-app payment processing.** Buyers and farmers settle outside the platform. Track `payment_status` only (`UNPAID`, `PAID`, `DISPUTED`), updated manually. |
| Order confirmation | An order is confirmed **only when the farmer accepts it**. No auto-confirmation. |
| Recommendations | Show on dashboards (a recommendations endpoint the app calls on load) **and** on request through the AI chat. |
| Farmer verification | No documents in the MVP. Add `is_verified` (default `False`, admin-editable only) to show a badge later. |
| Location privacy | GPS is optional and always private. Others see town, municipality and province plus approximate distance. |
| Cooperative priority | Groups → bulk purchasing → transport first. Then security, insurance, equipment and storage. |

---

## Part 1: Audit and finish Member 1 (backend foundation and AI agent)

Check each item below. Implement whatever is missing, fix whatever is broken, and add tests where coverage is missing.

- [ ] Django + DRF project; settings split (base/dev/test) and read from the environment; `.env.example`; `.env` is git-ignored
- [ ] Custom email-login `User` with `role` (`FARMER` / `WHOLESALE_BUYER`), not changeable through the API after registration
- [ ] JWT auth: register, login, refresh, logout (blacklist), `me` (GET/PATCH, role and email read-only), change-password
- [ ] `core`: `IsFarmer`, `IsWholesaleBuyer`, `IsOwnerOrReadOnly`, role helper, `TimeStampedModel`, pagination, the custom exception handler with the format `{"error": {"code", "message", "details"}}`, throttling, health check, OpenAPI schema and Swagger UI
- [ ] `locations`: `UserLocation` (the nine SA provinces, municipality, town, optional lat/lng (both or neither), `share_precise_location`, `preferred_delivery_areas`); `haversine_km`, `approximate_distance` with the no-GPS fallback tiers (`same_town` / `same_municipality` / `same_province` / `different_province`), `proximity_rank`; `GET/PUT/PATCH /api/v1/locations/me/`
- [ ] `ai`: `AIConversation`, `AIMessage`, `AIActionLog`, `PendingAction` (expires after 15 minutes); a Grok client using the `openai` SDK with the xAI base URL and `XAI_MODEL` from the environment (check xAI's current docs, don't hard-code a model), with timeouts, retry and a 503 on outage
- [ ] Tool registry: input serializer validation, role filtering (only allowed tools are sent to Grok), runs as the requesting user, logs every call
- [ ] Confirmation flow: confirmation-required tools create a `PendingAction` instead of executing; `POST /api/v1/ai/actions/{id}/confirm/` and `/cancel/`; owner only; single use; expiry enforced
- [ ] `POST /api/v1/ai/chat/` with the response shape `{conversation_id, reply, tool_calls, data, pending_action}`, at most 5 tool rounds, the system prompt rules (no invented data, no commitments, no insurance cover claims), messages persisted, conversation list and messages endpoints, a strict throttle
- [ ] `find_nearby_farmers` fully working; every other tool registered (stubs are fine until Parts 2–4 replace them)
- [ ] `seed_dev_data` management command; all models registered in the admin
- [ ] Docs: `README.md`, `docs/API_CONVENTIONS.md`, `docs/AI_AGENT.md`, `docs/INTEGRATION_GUIDE.md`

Then **extend `seed_dev_data`** as you build each later part, so the whole app can be demonstrated with realistic South African data. Use at least 8 farmers and 5 buyers across a few provinces, some with GPS and some without. Include produce listings, buyer requirements, orders in different states, groups, a bulk purchase, a transport request and equipment.

---

## Part 2: Member 2 — farmer profiles and produce marketplace

Apps: `apps/farmers`, `apps/listings`.

### Models
- `FarmerProfile` (one-to-one `User`, farmers only): `farm_name`, `bio`, `farm_size_hectares` (optional), `main_produce` (list or M2M to category), `is_verified` (admin-only), timestamps. Location comes from the existing `UserLocation`, so don't duplicate it.
- `ProduceCategory`: seeded with Vegetables, Fruits, Grains, Legumes, Livestock products, Dairy, Herbs, Other.
- `ProduceListing`: `farmer` (FK User), `produce_name` (e.g. "Tomatoes"; normalise for matching, e.g. a lower-case `produce_key`), `category`, `quantity_available` (Decimal), `unit` (`KG`, `TONNE`, `BAG`, `CRATE`, `BOX`, `DOZEN`, `LITRE`, `UNIT`), `price_per_unit` (ZAR), `quality_grade` (`PREMIUM`, `GRADE_A`, `GRADE_B`, `STANDARD`, `ORGANIC`, …), `available_from`, `available_until` (optional), `description`, `status` (`ACTIVE`, `PAUSED`, `SOLD_OUT`, `DELETED`; soft delete), timestamps.
- `ListingImage`: FK listing, `ImageField` (configure `MEDIA_ROOT`/`MEDIA_URL`; validate type and size ≤ 5 MB; max 5 images per listing). Pillow is required.
- Add a unit-conversion helper (`KG` ↔ `TONNE` at minimum) for quantity matching. Non-convertible units only match the same unit.

### Endpoints
- `GET/PUT/PATCH /api/v1/farmers/me/profile/` (the farmer's own profile)
- `GET /api/v1/farmers/{id}/`: public farmer profile (display name, farm name, town, municipality and province, approximate distance from the requester, verification badge, active listings count, completed orders count). No coordinates, email or phone.
- `GET/POST /api/v1/listings/mine/`, `GET/PATCH/DELETE /api/v1/listings/mine/{id}/`, `POST .../pause/`, `POST .../resume/`, `POST/DELETE .../images/`
- Only the owning farmer can edit, pause or delete. Buyers can't create listings.

### Services (in `apps/listings/services.py` and `apps/farmers/services.py`)
- `create_or_update_listing(user, data) -> dict`: used by the API and by the AI tool. **Replace the AI stub.** The tool stays `requires_confirmation=True`.
- `search_buyer_requirements(user, produce=None, listing_id=None, max_distance_km=None) -> list[BuyerMatch]`: farmer → buyer matching (coordinate the scoring with Part 3 via a shared `apps/recommendations/scoring.py`). Matches open `BuyerRequirement`s for produce the farmer lists, compares quantity needed vs. the farmer's available stock (partial supply allowed but labelled), checks delivery area and proximity, and checks the needed-by date vs. availability. Each match includes `match_reasons` and `gaps`. **Replace the AI stub.**
- `GET /api/v1/farmers/me/recommended-buyers/` (dashboard recommendations)

### Tests
Farmer-only permissions, owner-only edits, buyers blocked, soft delete and pause hide listings from search, image validation, unit conversion, buyer matching (including no-match and partial-quantity cases), no coordinates in responses.

---

## Part 3: Member 3 — wholesale buyer marketplace, recommendations and orders

Apps: `apps/buyers`, `apps/recommendations`, `apps/orders`, `apps/messaging`.

### Models
- `WholesaleBuyerProfile` (one-to-one `User`, buyers only): `business_name`, `business_type` (`RESTAURANT`, `SUPERMARKET`, `GROCERY`, `DISTRIBUTOR`, `PROCESSOR`, `WHOLESALER`, `OTHER`), `description`, `produce_interests` (categories / produce keys), timestamps. Business location and preferred delivery areas come from `UserLocation`.
- `BuyerRequirement`: `buyer`, `produce_name`/`produce_key`, `category`, `quantity_needed`, `unit`, `max_price_per_unit` (optional), `min_quality_grade` (optional), `needed_by` (date), `max_distance_km` (optional), `recurring` (`NONE`, `WEEKLY`, `MONTHLY`), `notes`, `status` (`OPEN`, `FULFILLED`, `CLOSED`), timestamps.
- `RecommendationLog`: who asked, direction (`BUYER_TO_FARMER` / `FARMER_TO_BUYER`), input criteria, result IDs and scores, source (`dashboard` / `ai` / `api`), timestamp.
- `Order`: `buyer`, `farmer`, `status`, `payment_status` (`UNPAID`/`PAID`/`DISPUTED`), `delivery_date`, `delivery_notes`, `total_amount`, `rejection_reason`, `buyer_requirement` (optional FK), timestamps.
- `OrderItem`: `order`, `listing`, a snapshot of `produce_name`, `unit` and `price_per_unit` at order time, `quantity`, `line_total`.
- `OrderStatusHistory`: order, from_status, to_status, changed_by, note, timestamp.
- `Conversation` (participants: one buyer, one farmer, optional order) and `Message` (sender, body, `read_at`). Only participants can read or write.

### Order state machine (enforce it in one service, never ad hoc in views)
```
PENDING ──farmer accepts──▶ ACCEPTED ──farmer──▶ DISPATCHED ──buyer confirms receipt──▶ DELIVERED ──▶ COMPLETED
   │                           │
   ├─farmer rejects──▶ REJECTED │
   └─buyer cancels──▶ CANCELLED ◀─either party, before DISPATCHED (with reason)
```
- An order may contain items from **one farmer only**.
- On **accept**: inside `transaction.atomic()`, lock the listings (`select_for_update`), check stock, decrement `quantity_available`, and set `SOLD_OUT` at 0. If stock is insufficient, fail with a clear error.
- On **cancel after accept**: restore the stock.
- Every transition writes `OrderStatusHistory` and sends a notification record (a simple `Notification` model in `core` is fine: user, type, message, link, read flag). The app polls it, so no push notifications are needed.
- Buyers only see their own orders. Farmers only see orders addressed to them.

### Marketplace search and comparison
- `GET /api/v1/marketplace/listings/`: active listings only. Filters: `q` (produce name), `category`, `min_price`/`max_price`, `min_quantity` (unit-aware), `quality_grade`, `province`/`municipality`/`town`, `max_distance_km` (from the buyer's location; uses GPS when both sides have it, otherwise the proximity tiers), `available_by`. Sorting: price, distance, quantity, newest. Paginated.
- `GET /api/v1/marketplace/compare/?listing_ids=1,2,3`: side-by-side comparison (price, quantity, quality, distance, availability, farmer reliability).
- `GET /api/v1/marketplace/farmers/`: farmer discovery with location and produce filters.

### Recommendation engine (`apps/recommendations/scoring.py`, shared with Part 2)
`search_recommended_farmers(user, produce, quantity, unit, max_price=None, min_quality=None, needed_by=None, max_distance_km=None, requirement_id=None) -> list[FarmerMatch]`. **Replace the AI stub.**

- **Hard filters:** produce match, listing ACTIVE, available on or before `needed_by` (when given), within `max_distance_km` or the delivery areas when given. **Never** return farmers with none of the produce.
- **Score (0–100), with weights in one settings dict so they're easy to tune:** quantity coverage 30 (full coverage scores highest; partial is allowed but must be labelled with a `shortfall`), price 20 (relative to the median of the candidates and to `max_price`), distance/proximity 20, availability timing 10, quality 10, reliability 10 (completed / (completed + rejected + cancelled-by-farmer) once the farmer has ≥ 3 orders; otherwise neutral, and say so).
- **Each `FarmerMatch` includes:** farmer display name and ID, listing ID, produce, available quantity and unit, price, quality, town/municipality/province, approximate distance and its basis, score, `match_reasons` (plain-language strings, e.g. "Has 120 kg available — covers your 100 kg", "≈ 18 km away", "Price R12/kg is below the median R14/kg"), and `shortfall` when relevant (e.g. "Only 60 kg of your 100 kg").
- Multi-item needs (e.g. 100 kg tomatoes + 50 kg potatoes) are supported by returning a result per item, plus farmers who can supply several items flagged as `covers_multiple`.
- Log every run in `RecommendationLog`.
- **Endpoints:** `GET /api/v1/buyers/me/recommended-farmers/` (dashboard, based on the buyer's open requirements), `POST /api/v1/recommendations/farmers/` (ad hoc criteria).

### AI tools to add (register and test)
- `compare_listings` (buyer, no confirmation)
- `create_order` (buyer, **confirmation required**: the pending summary lists the farmer, items, quantities, prices and total)
- `get_my_orders` (both roles, no confirmation)
- `respond_to_order` (farmer accept or reject, **confirmation required**)

### Tests
Profile and role permissions, requirement CRUD, every search filter, distance filtering with and without GPS, scoring order and reasons, shortfall labelling, no farmers without stock returned, every legal and illegal order transition, stock decrement and restore, concurrent-accept safety (two accepts racing for the last stock: one must fail), single-farmer orders, messaging participant permissions, AI order creation stays pending until confirmed.

---

## Part 4: Member 4 — cooperative features and shared services

Apps: `apps/groups`, `apps/bulk`, `apps/transport`, `apps/services` (security + insurance), `apps/equipment`. All of these are **farmer-only** features.

### 4.1 Farmer groups
- `FarmerGroup` (name, description, `group_type`: `LOCATION`, `PRODUCE`, `INTEREST`, `PURCHASING`, `TRANSPORT`; province/municipality/town; `is_open` join policy; created_by), `GroupMembership` (role `ADMIN`/`MEMBER`, status `ACTIVE`/`INVITED`/`REQUESTED`/`LEFT`/`REMOVED`), `GroupPost` (announcements and discussion, with an `is_announcement` flag that only admins can set).
- Endpoints: create, list and search (by location, type, produce), detail, join (open = immediate; closed = request → admin approves), invite (by farmer ID), accept or decline an invitation, leave, remove a member (admin), promote to admin, posts.
- At least one admin must remain in a group.

### 4.2 Bulk purchasing
- `BulkPurchase`: group (optional) or open to nearby farmers, `item_name`, `category` (fertiliser, seed, pesticide, feed, irrigation, tools, other), `unit`, `unit_price`, `discount_tiers` (JSON list of `{min_total_quantity, unit_price}`), optional `supplier_name`/`supplier_contact` (free text: suppliers have no accounts), `deadline`, `status` (`OPEN`, `LOCKED`, `ORDERED`, `COMPLETED`, `CANCELLED`), organiser.
- `BulkPurchaseMember`: farmer, quantity, `calculated_contribution`, `confirmed` (bool + timestamp), `payment_status` (`UNPAID`/`PAID`), timestamps.
- **`calculate_cost_shares(bulk_purchase or ad hoc lines, method="quantity")`** (pure function, heavily unit-tested): total quantity → applicable discount tier → unit price → each member's share = quantity × unit price. Optional `shared_fees` (e.g. delivery) are split by quantity share. Round to cents and give the rounding remainder to the largest contributor, so the shares sum exactly to the total. Return the total, applied tier, savings vs. buying individually, and the per-member breakdown.
  - Worked example to test: 5 + 8 + 7 + 10 = 30 bags.
- Joining or changing quantity recalculates everyone's share. **Joining and confirming are separate.** Confirmation is an explicit user action (in the app and through an AI `PendingAction`). The organiser can lock the purchase only when every member has confirmed.

### 4.3 Shared transport
- `TransportRequest`: organiser, pickup area (province/municipality/town), destination (free text + town), `travel_date`, `vehicle_description`, `total_cost` (optional until quoted), `capacity` (optional, with a unit), `cost_split_method` (`WEIGHT`, `VOLUME`, `DISTANCE`, `SPACE`, `EQUAL`, `AGREED`), status (`OPEN`, `FULL`, `CONFIRMED`, `COMPLETED`, `CANCELLED`).
- `TransportParticipant`: farmer, load weight/volume/space, pickup town, optional agreed amount, `calculated_share`, `confirmed`.
- Cost allocation reuses the same rounding approach. `DISTANCE` uses each participant's approximate distance to the destination when GPS is available, otherwise the proximity tier weights; document the formula. `AGREED` uses the entered amounts and validates that they sum to the total.
- Matching: `find_transport_requests(user, destination=None, date=None)` ranks open requests by pickup proximity, then destination match, then date closeness.

### 4.4 Shared security
- Use `SharedServiceRequest` (`service_type=SECURITY`; title, description, area, `total_monthly_cost`, `split_method`, status) and `ServiceContribution` (farmer, amount, confirmed).
- Add `SecurityAlert` posts scoped to an area or group (information sharing only, never personal data about suspects).

### 4.5 Insurance information
- `InsuranceProduct` (admin-managed info: provider name, `category` (`CROP`, `LIVESTOCK`, `EQUIPMENT`, `PROPERTY`), summary, provider contact or website, `is_authorised_provider` flag) and `InsuranceQuoteRequest` (farmer, product or category, details, status `SUBMITTED`/`QUOTED`/`CLOSED`, a quote note and amount entered by an admin).
- The app and the AI must **never** state or imply that a farmer is covered or insured. Show a standard disclaimer on all insurance responses.

### 4.6 Shared equipment and storage
- `EquipmentListing`: owner, `type` (`TRACTOR`, `IRRIGATION`, `HARVESTER`, `TOOLS`, `COLD_STORAGE`, `WAREHOUSE`, `MACHINERY`, `OTHER`), name, description, `rate` + `rate_unit` (per hour, day or month; or per tonne per day for storage), `capacity` (for storage), location (from the owner), `is_available`.
- `EquipmentBooking`: listing, requester, `start`, `end`, `quantity` (storage capacity requested), status (`REQUESTED`, `APPROVED`, `DECLINED`, `CANCELLED`, `COMPLETED`), `estimated_cost`.
- **No overlapping APPROVED bookings** for equipment (check inside a transaction). Storage allows concurrent bookings up to capacity. Only the owner approves or declines. Booking requests through the AI need confirmation.

### AI tools: replace the stubs and add these
`find_bulk_purchases`, `calculate_cost_shares`, `find_transport_requests`, `find_farmer_groups`, `find_equipment` (no confirmation). Add `join_bulk_purchase`, `confirm_bulk_purchase_contribution`, `join_transport_request` and `request_equipment_booking` (all **confirmation required**). Also `find_nearby_farmers` filtered by produce or interest, if it isn't already.

### Tests
Group admin rules, invitations and join requests, the bulk-purchase calculation (the worked example, discount tiers, rounding sums exactly, fees), recalculation on join and leave, lock only after all confirm, transport splits for every method, AGREED validation, booking overlap rejection, storage capacity, insurance disclaimer present, buyers blocked from every cooperative endpoint, AI confirmation for every commitment tool.

---

## Part 5: Member 5 — React Native mobile app

Create `mobile/` at the repo root (if it doesn't exist) using **Expo + TypeScript**.

### Stack
- Expo (managed), TypeScript (strict), React Navigation (auth stack + role-based bottom tabs + nested stacks)
- `@tanstack/react-query` for server state; `axios` API client with a JWT interceptor (attach the access token; on 401, refresh once and retry; on refresh failure, log out)
- `expo-secure-store` for tokens (never AsyncStorage for tokens)
- `react-hook-form` + `zod` for forms
- `expo-image-picker` for listing images; `expo-location` **only** if the user chooses to share GPS (opt-in with a clear explanation)
- API base URL from `EXPO_PUBLIC_API_URL` (document using the machine's LAN IP for a physical device). **No xAI key or AI calls from the app:** it only calls `/api/v1/ai/chat/`.
- Types for API responses: generate them from the OpenAPI schema (`openapi-typescript`) and add an npm script to regenerate them.

### Screens
- **Auth:** welcome, register (role choice: Farmer / Wholesale Buyer), login, forgot-password placeholder.
- **Onboarding:** profile + location setup (province picker, municipality, town, optional "share precise location" toggle with an explanation).
- **Farmer tabs:**
  - Dashboard: recommended buyers, open orders, group activity, notifications
  - My Listings: list, create/edit with images, pause/resume, delete
  - Orders: incoming, accept/reject, status updates, history
  - Co-op hub: groups, bulk purchases with a contribution breakdown and confirm button, transport, security, insurance info and quote request, equipment and storage with booking
  - Assistant (AI chat)
  - Profile
- **Buyer tabs:**
  - Dashboard: recommended farmers with reasons and shortfalls, my requirements, active orders
  - Marketplace: search with filters (category, price, quantity, quality, location, distance), listing detail, farmer profile, compare up to 3
  - Requirements: CRUD
  - Orders: place, track, history, confirm receipt
  - Assistant
  - Profile
- **Messages:** conversation list and thread (polling is fine).
- **Notifications:** list with unread badge (polling).

### AI chat UX
- Chat bubbles. Tool results in `data` render as tappable cards (farmer match card, buyer match card, listing card, bulk-purchase breakdown, etc.) that navigate to the related screen.
- When the response contains `pending_action`, show a **confirmation card** with the summary and Confirm / Cancel buttons, calling the confirm or cancel endpoints. Show expiry. Nothing is committed without this tap.
- Show a "may take a moment" state; handle 503 (AI unavailable) gracefully.

### Quality bar
- Loading, empty and error states on every screen; pull-to-refresh on lists; form validation messages from the API error format; accessible labels; works on small Android screens.
- Distances are always shown as "≈ 12 km away" or "Same municipality" — never coordinates.
- Basic tests with Jest + React Native Testing Library for the API client (token refresh), the auth flow, the confirmation card and one listing form. `npm run lint` and `npx tsc --noEmit` pass.

---

## Part 6: Integration, testing and handover

1. Run the whole backend suite plus `check` and `makemigrations --check`; the mobile `tsc`, lint and tests. Everything must pass.
2. Run `seed_dev_data`. Start the API and the Expo app, and walk through these **end-to-end scenarios** (scripted as API integration tests where practical):
   - A buyer registers, sets their location, posts "100 kg tomatoes + 50 kg potatoes within 5 days, ≤ 50 km", and gets ranked farmer recommendations with reasons.
   - The buyer asks the AI "Find farmers selling 100 kg of tomatoes near me". The results match the database, and nothing is invented.
   - The buyer orders through the AI → a pending confirmation appears → they confirm → the farmer accepts → stock goes down → dispatched → delivered → completed.
   - A farmer with 500 kg of potatoes sees matching buyers on their dashboard and through the AI.
   - Four farmers join a fertiliser bulk purchase (5/8/7/10 bags) → the shares are correct → each confirms → the organiser locks it.
   - Three farmers share transport to the same market, split by weight.
   - A farmer books a tractor; an overlapping booking is rejected.
   - A buyer tries to access a cooperative endpoint → 403. A user tries to read another user's coordinates → never exposed.
3. Verify every item in the **MVP acceptance criteria** below, and record the result of each in `PROGRESS.md`.
4. Update the docs: `README.md` (backend + mobile setup), `docs/API_CONVENTIONS.md`, `docs/AI_AGENT.md` (full tool list with roles and confirmation flags), `docs/INTEGRATION_GUIDE.md`, `docs/DECISIONS.md`, and a short `docs/DEMO_SCRIPT.md` for presenting the MVP.

### MVP acceptance criteria
**Auth and profiles:** farmers and buyers can register and log in · correct role-based functionality · profiles manageable · location can be provided.
**Marketplace:** farmers publish listings and update quantity and price · buyers search, filter, view farmer info, post requirements and place orders · farmers manage incoming orders.
**AI:** buyers get farmer recommendations · farmers get buyer recommendations · recommendations use real records and explain why · Grok retrieves data only through approved tools · Grok cannot bypass permissions · consequential actions require confirmation.
**Location:** province, municipality and town selectable · GPS optional · approximate distances when coordinates exist · matching works without GPS · no maps integration.
**Cooperative:** create and join groups · create and join bulk purchases · contributions calculated · transport coordinated · shared services coordinated · equipment listed and booked.

---

## How to work
- Do the parts in order (1 → 6). Within a part, build models → migrations → services (with unit tests) → serializers and views → endpoint tests → AI tools → seed data → docs.
- Keep views thin and put business logic in `services.py`, which the API, the AI tools and the tests all use.
- Commit at least once per sub-part with a clear message (e.g. `orders: state machine and stock reservation`).
- If something in this prompt is ambiguous, choose the simplest option consistent with §0.2 and §0.4, record it in `docs/DECISIONS.md`, and carry on. Don't stop to ask.
- If you cannot finish everything in this session, stop at a clean boundary (tests passing, committed), update `PROGRESS.md` with exactly what's left, and tell me.

When finished, reply with a short summary: what was built in each part, how to run the backend and the app, the test results, decisions and assumptions made, and any known gaps.
