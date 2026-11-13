# MVP demo script (about 10 minutes)

**Setup:** `python manage.py seed_dev_data`, then `runserver 0.0.0.0:8000`, then `npx expo start` in
`mobile/`. Every demo password is `Dev-Passw0rd-2026`. For the assistant parts, set `XAI_API_KEY` and
`XAI_MODEL` in `backend/.env`. Without them the app shows a friendly "assistant unavailable" message and
everything else still works.

## 1. Buyer: find and compare (3 min)

Log in as **chef.buyer@example.com** (Rosebank Bistro, Johannesburg, GPS on).

1. **Dashboard → Recommended farmers.** The bistro's requirements (100 kg tomatoes and 50 kg potatoes,
   within 50 km) show ranked farmers. Point out:
   - the score and the plain-language reasons ("Has 120 kg available, covering your 100 kg", "≈ 7 km away",
     "Price R12.50/kg is below the median…");
   - shortfall labels ("Only 80 kg of your 100 kg");
   - distances are approximate: "≈ 12 km" or "Same municipality", never coordinates.
2. **Marketplace.** Search "tomatoes", then open **Filters** and set *Within 50 km* and sort *Cheapest*.
   Tick ☐ on 2–3 listings and tap **Compare**: price, stock, quality, distance and the farmer's completed
   orders side by side.
3. Open a listing, then **Farmer profile**: verified badge and completed-order count, with no phone, email
   or address shown.

## 2. Buyer: order through the assistant (2 min)

1. **Assistant →** "Find farmers selling 100 kg of tomatoes near me." The cards are real listings from
   the database.
2. "Order 20 kg from Thandi's Vegetable Farm." A **Please confirm** card appears with farmer, quantity,
   price and total. Nothing is ordered yet.
3. Tap **Confirm**. **Orders** now shows the order as *Waiting for farmer*.

## 3. Farmer: accept and fulfil (2 min)

Log in as **thandi.farmer@example.com**.

1. **Dashboard:** *Buyers looking for your produce*, with match reasons, plus the new order under
   *Open orders*.
2. Open the order → **Accept**. Stock is reserved: **My listings** shows the reduced quantity.
   **Mark dispatched**. Switch back to the buyer: **Confirm received** → **Mark complete**.
3. **My listings → + New listing**: create a listing and add a photo. Show **Pause** and **Resume**.

## 4. Cooperative (2 min)

Still as Thandi, open **Co-op hub**:

1. **Bulk buying → LAN fertiliser.** The contribution breakdown shows the discount tier and each
   member's exact share (shares always add up to the total). **Join**/change quantity, then
   **Confirm my contribution**. Joining and confirming are separate steps.
2. **Shared transport →** the Soweto trip to Joburg Market: shares split by load weight.
3. **Equipment & storage →** book the tractor. A second, overlapping booking is rejected once the
   owner approves the first.
4. **Insurance info:** the disclaimer is always shown. The app never claims anyone is covered.

## 5. Safety points to mention (1 min)

- Grok only calls approved tools; it never touches the database or confirms anything itself.
- Every tool call is in the AI action log (Django admin → AI action logs).
- Buyers can't open any cooperative feature (they get a 403).
- The xAI key exists only on the server.
