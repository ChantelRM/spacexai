import axios, { AxiosAdapter, AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

import { createApiClient, TokenStore } from '../src/api/client';

function memoryStore(access: string | null, refresh: string | null): TokenStore & { access: string | null; refresh: string | null } {
  const store = {
    access, refresh,
    getAccess: async () => store.access,
    getRefresh: async () => store.refresh,
    setTokens: async (t: { access: string; refresh?: string }) => {
      store.access = t.access;
      if (t.refresh) store.refresh = t.refresh;
    },
    clear: async () => {
      store.access = null;
      store.refresh = null;
    },
  };
  return store;
}

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown = {}): AxiosResponse | never {
  const response = { data, status, statusText: String(status), headers: {}, config } as AxiosResponse;
  if (status >= 400) throw new AxiosError('fail', String(status), config, null, response);
  return response;
}

/** Fake server: 200 only for the "fresh" access token. */
const adapter: jest.MockedFunction<AxiosAdapter> = jest.fn(async (config) => {
  const auth = config.headers?.Authorization ?? config.headers?.get?.('Authorization');
  return respond(config, auth === 'Bearer fresh' ? 200 : 401, { ok: true });
});

afterEach(() => jest.restoreAllMocks());

test('attaches the access token and refreshes once on 401, then retries', async () => {
  const tokens = memoryStore('stale', 'refresh-1');
  const onSessionExpired = jest.fn();
  const refresh = jest.spyOn(axios, 'post').mockResolvedValue({ data: { access: 'fresh', refresh: 'refresh-2' } });
  const client = createApiClient({ baseURL: 'http://api', tokens, onSessionExpired });
  client.defaults.adapter = adapter;

  // Two concurrent requests share ONE refresh.
  const [a, b] = await Promise.all([client.get('/orders/'), client.get('/listings/mine/')]);
  expect(a.data).toEqual({ ok: true });
  expect(b.data).toEqual({ ok: true });
  expect(refresh).toHaveBeenCalledTimes(1);
  expect(refresh).toHaveBeenCalledWith('http://api/auth/refresh/', { refresh: 'refresh-1' }, expect.anything());
  expect(tokens.access).toBe('fresh');
  expect(tokens.refresh).toBe('refresh-2'); // rotated refresh token saved
  expect(onSessionExpired).not.toHaveBeenCalled();
});

test('logs out when the refresh fails', async () => {
  const tokens = memoryStore('stale', 'expired-refresh');
  const onSessionExpired = jest.fn();
  jest.spyOn(axios, 'post').mockRejectedValue(new Error('401'));
  const client = createApiClient({ baseURL: 'http://api', tokens, onSessionExpired });
  client.defaults.adapter = adapter;

  await expect(client.get('/orders/')).rejects.toBeInstanceOf(AxiosError);
  expect(onSessionExpired).toHaveBeenCalledTimes(1);
  expect(tokens.access).toBeNull();
  expect(tokens.refresh).toBeNull();
});

test('does not try to refresh for the login call itself', async () => {
  const tokens = memoryStore(null, null);
  const refresh = jest.spyOn(axios, 'post');
  const client = createApiClient({ baseURL: 'http://api', tokens, onSessionExpired: jest.fn() });
  client.defaults.adapter = adapter;
  await expect(client.post('/auth/login/', { email: 'a', password: 'b' })).rejects.toBeInstanceOf(AxiosError);
  expect(refresh).not.toHaveBeenCalled();
});
