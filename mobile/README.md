# Mobile app (Expo + TypeScript)

React Native app for farmers and wholesale buyers. It talks only to the Django API (`/api/v1/`) and never
holds an AI key: the assistant goes through `/api/v1/ai/chat/`.

## Run

```bash
npm install
cp .env.example .env     # set EXPO_PUBLIC_API_URL (see below)
npx expo start           # a = Android, i = iOS, w = web, or scan the QR code with Expo Go
```

`EXPO_PUBLIC_API_URL` must point at the backend's `/api/v1`:

| Where the app runs | URL |
|---|---|
| Android emulator | `http://10.0.2.2:8000/api/v1` |
| iOS simulator / web | `http://127.0.0.1:8000/api/v1` |
| Physical phone on the same Wi-Fi | `http://<your computer's LAN IP>:8000/api/v1`. Run the API with `runserver 0.0.0.0:8000` and add the IP to `ALLOWED_HOSTS`. |

## Scripts

| Script | What |
|---|---|
| `npm test` | Jest + React Native Testing Library |
| `npm run typecheck` | `tsc --noEmit` (strict) |
| `npm run lint` | `expo lint` |
| `npm run gen:api` | Regenerate `src/api/schema.d.ts` from a running backend (`http://127.0.0.1:8000/api/schema/?format=json`) |
| `npm run gen:api:file` | Regenerate from the committed `openapi.json` snapshot |

## Structure

```
App.tsx                      providers: safe area, react-query, auth, navigation
src/api/                     axios client (JWT + one-shot refresh), endpoints, error parsing, generated types
src/auth/AuthContext.tsx     session: secure-store tokens, login/register/logout, session-expiry logout
src/navigation/              auth stack → onboarding → role tabs + detail stack
src/screens/                 auth, onboarding, farmer, buyer, shared, coop, assistant
src/components/              listing form, match/listing/order cards, AI confirmation card
src/ui/                      theme, basic components, QueryScreen (loading/error/empty/refresh)
__tests__/                   client refresh, auth flow, confirmation card, listing form
```

## Rules this app follows

- Tokens live in `expo-secure-store`, never AsyncStorage.
- On 401 the client refreshes once (concurrent requests share the refresh), saves the rotated refresh
  token, retries, and logs out if refreshing fails.
- GPS is opt-in, with an explanation; it's only requested when the user turns it on. Other people's
  locations are shown as "≈ 12 km away" or "Same municipality", never coordinates.
- Anything the assistant proposes appears as a confirmation card. Nothing is committed without that tap.
- Server form errors (`{"error": {"details": {...}}}`) are shown under the matching inputs.
- Lists poll for updates: notifications and orders every 15 s, open message threads every 5 s. There are
  no push notifications in the MVP.

Native modules used (`expo-secure-store`, `expo-image-picker`, `expo-location`) are included in Expo Go
for this SDK. For a store build, use EAS (`npx eas-cli@latest build`).
