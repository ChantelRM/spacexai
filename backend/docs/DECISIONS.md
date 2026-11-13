# Product and technical decisions

These are defaults the team hasn't finalised. Each one is kept easy to change; the "Where" column shows where.

## Product defaults

| Decision | Default implemented | Where to change |
|---|---|---|
| Payments | No in-app payment processing. Buyers and farmers settle outside the platform. Orders, bulk-purchase members and contributions track `payment_status` only (`UNPAID`, `PAID`, `DISPUTED`), updated manually. | `apps/orders/models.py` |
| Order confirmation | An order is confirmed only when the farmer accepts it. There is no auto-confirmation. | `apps/orders/services.py` |
| Recommendations | Shown on dashboards (`/farmers/me/recommended-buyers/`, `/buyers/me/recommended-farmers/`) and on request through the AI chat. | |
| Farmer verification | No documents in the MVP. `FarmerProfile.is_verified` defaults to `False` and can only be changed in Django admin. | `apps/farmers` |
| Location privacy | GPS is optional and always private. Others see town, municipality and province plus an approximate distance. | `apps/locations` |
| Cooperative priority | Groups, bulk purchasing and transport first; then security, insurance, equipment and storage. | |

## Technical decisions

| Decision | Why |
|---|---|
| Docs live in `backend/docs/`, not a top-level `docs/`. | Existing convention from the foundation work. |
| Grok uses the xAI **Responses API**, stateless (`store=False`). | xAI's docs mark Chat Completions as legacy. Our database is the record of the conversation. |
| AI tool services are found by dotted path in `apps/ai/services_contract.py` (`SERVICE_PROVIDERS`). | Feature apps plug in without editing the AI app. The provider paths now point at each app's `services.py`. |
| Units are upper-case codes (`KG`, `TONNE`, `BAG`, `CRATE`, `BOX`, `DOZEN`, `LITRE`, `UNIT`) shared by listings, requirements and AI tools. Only `KG` and `TONNE` convert into each other. | The listing spec uses these codes, and the AI tools must accept the same values the database stores. The earlier lower-case AI units were replaced. |
| Produce matching uses `produce_key`: the produce name lower-cased, with spaces collapsed and a simple plural stripped ("Tomatoes" → "tomato"). | Simple and predictable without a produce catalogue. Swap in a synonym table later. |
| Distance filters without GPS use the tier estimates in `apps/locations/distance.py` (same town ≈ 5 km, same municipality ≈ 30 km, same province ≈ 150 km, other province ≈ 600 km). | Lets "within 50 km" work for users without GPS. It is approximate by design. |
| Recommendation weights live in `settings.RECOMMENDATION_WEIGHTS`. | Easy to tune without code changes. |
| Reliability is neutral (half of its weight) until a farmer has 3 or more finished orders. | Avoids punishing new farmers. Match reasons say so. |
| Notifications are database rows the app polls. There are no push notifications. | MVP scope. |
| Payments, insurance quotes and verification are manual and admin-driven. | No payment or insurance integrations in the MVP. |
| Insurance responses always carry a disclaimer, and the AI is told never to claim cover. | Regulatory safety. |
| Cost-share rounding: shares are rounded to cents, and the remainder goes to the largest contributor, so the shares always sum exactly to the total. | As specified. |
| `DISTANCE` transport split: weight = approximate km from the participant's pickup to the destination town (GPS haversine when both are known, otherwise the tier estimate). Each share = total × weight ÷ Σweights. | Documented formula that works without GPS. |
| Images are stored on the local disk (`MEDIA_ROOT`) and served by Django only when `DEBUG` is on. | Use object storage in production. |
