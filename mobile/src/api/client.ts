import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

/**
 * Token storage the client depends on. The app passes the secure-store
 * implementation (src/api/tokens.ts); tests pass an in-memory one.
 */
export interface TokenStore {
  getAccess(): Promise<string | null>;
  getRefresh(): Promise<string | null>;
  setTokens(tokens: { access: string; refresh?: string }): Promise<void>;
  clear(): Promise<void>;
}

export interface ApiClientOptions {
  baseURL: string;
  tokens: TokenStore;
  /** Called once when the session can't be refreshed (the app logs the user out). */
  onSessionExpired: () => void;
  timeoutMs?: number;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean; _skipAuth?: boolean };

const AUTH_PATHS = ['/auth/login/', '/auth/register/', '/auth/refresh/'];

/**
 * Axios client for /api/v1 with JWT handling:
 * - attaches the access token,
 * - on 401 refreshes ONCE (concurrent 401s share one refresh) and retries,
 * - if refresh fails, clears tokens and calls onSessionExpired.
 */
export function createApiClient({ baseURL, tokens, onSessionExpired, timeoutMs = 30000 }: ApiClientOptions) {
  const client: AxiosInstance = axios.create({ baseURL, timeout: timeoutMs });
  let refreshing: Promise<string | null> | null = null;

  async function refreshAccess(): Promise<string | null> {
    const refresh = await tokens.getRefresh();
    if (!refresh) return null;
    try {
      // Plain axios: must not go through our interceptors.
      const res = await axios.post(`${baseURL}/auth/refresh/`, { refresh }, { timeout: timeoutMs });
      await tokens.setTokens({ access: res.data.access, refresh: res.data.refresh });
      return res.data.access as string;
    } catch {
      return null;
    }
  }

  client.interceptors.request.use(async (config: RetriableConfig) => {
    const isAuthCall = AUTH_PATHS.some((p) => config.url?.endsWith(p));
    if (!isAuthCall && !config._skipAuth) {
      const access = await tokens.getAccess();
      if (access) config.headers.set('Authorization', `Bearer ${access}`);
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const config = error.config as RetriableConfig | undefined;
      const isAuthCall = AUTH_PATHS.some((p) => config?.url?.endsWith(p));
      if (error.response?.status !== 401 || !config || config._retried || isAuthCall) {
        throw error;
      }
      config._retried = true;
      refreshing = refreshing ?? refreshAccess().finally(() => {
        refreshing = null;
      });
      const access = await refreshing;
      if (!access) {
        await tokens.clear();
        onSessionExpired();
        throw error;
      }
      config.headers.set('Authorization', `Bearer ${access}`);
      return client.request(config);
    },
  );

  return client;
}
