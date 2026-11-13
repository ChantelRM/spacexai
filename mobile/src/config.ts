/**
 * API base URL. Set EXPO_PUBLIC_API_URL in mobile/.env:
 * - Android emulator: http://10.0.2.2:8000/api/v1
 * - iOS simulator / web: http://127.0.0.1:8000/api/v1
 * - Physical phone: http://<your computer's LAN IP>:8000/api/v1 (and add that IP to the backend ALLOWED_HOSTS)
 *
 * The app never holds an AI key: it only calls /api/v1/ai/chat/.
 */
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8000/api/v1').replace(/\/$/, '');

export const POLL_INTERVAL_MS = 15000;
