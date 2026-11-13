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
- [ ] `farmers`: `FarmerProfile`, public profile, recommended buyers
- [ ] `listings`: categories, listings, images, units, pause/resume/soft delete
- [ ] `create_or_update_listing` and `search_buyer_requirements` services wired to the AI

## Part 3: Buyers, recommendations, orders, messaging (Member 3)
- [ ] `buyers`: profile, requirements
- [ ] `recommendations`: scoring, logs, endpoints
- [ ] `orders`: state machine, stock reservation, history, notifications
- [ ] marketplace search, compare, farmer discovery
- [ ] `messaging`
- [ ] AI tools: `search_recommended_farmers`, `compare_listings`, `create_order`, `get_my_orders`, `respond_to_order`

## Part 4: Cooperative (Member 4)
- [ ] groups · [ ] bulk purchasing · [ ] transport · [ ] security/insurance services · [ ] equipment/storage
- [ ] AI tools wired, plus the commitment tools with confirmation

## Part 5: Mobile app (Member 5)
- [ ] Expo + TypeScript app in `mobile/`

## Part 6: Integration and handover
- [ ] End-to-end scenarios · [ ] acceptance criteria · [ ] docs and demo script

## Notes
- Pillow installs from a downloaded wheel: `pip install Pillow` intermittently failed to resolve on this machine.
