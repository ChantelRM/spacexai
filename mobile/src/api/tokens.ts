import * as SecureStore from 'expo-secure-store';

import type { TokenStore } from './client';

const ACCESS = 'coop.access';
const REFRESH = 'coop.refresh';

/** JWTs live only in the device keychain/keystore (never AsyncStorage). */
export const secureTokenStore: TokenStore = {
  getAccess: () => SecureStore.getItemAsync(ACCESS),
  getRefresh: () => SecureStore.getItemAsync(REFRESH),
  async setTokens({ access, refresh }) {
    await SecureStore.setItemAsync(ACCESS, access);
    if (refresh) await SecureStore.setItemAsync(REFRESH, refresh);
  },
  async clear() {
    await SecureStore.deleteItemAsync(ACCESS);
    await SecureStore.deleteItemAsync(REFRESH);
  },
};
