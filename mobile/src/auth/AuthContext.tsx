import { useQueryClient } from '@tanstack/react-query';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { auth, onSessionExpired } from '../api';
import type { TokenStore } from '../api/client';
import { secureTokenStore } from '../api/tokens';
import type { Role, User } from '../api/types';

type Status = 'loading' | 'signedOut' | 'signedIn';

interface AuthState {
  status: Status;
  user: User | null;
  role: Role | null;
  login: (email: string, password: string) => Promise<void>;
  register: (body: { email: string; password: string; role: Role; display_name: string; phone_number?: string })
    => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

interface ProviderProps {
  children: React.ReactNode;
  /** Injectable for tests. */
  tokens?: TokenStore;
  api?: Pick<typeof auth, 'login' | 'register' | 'logout' | 'me'>;
}

export function AuthProvider({ children, tokens = secureTokenStore, api = auth }: ProviderProps) {
  const [status, setStatus] = useState<Status>('loading');
  const [user, setUser] = useState<User | null>(null);
  const queryClient = useQueryClient();

  const signOutLocally = useCallback(async () => {
    await tokens.clear();
    queryClient.clear();
    setUser(null);
    setStatus('signedOut');
  }, [tokens, queryClient]);

  // Restore the session on launch.
  useEffect(() => {
    let alive = true;
    (async () => {
      const access = await tokens.getAccess();
      if (!access) {
        if (alive) setStatus('signedOut');
        return;
      }
      try {
        const me = await api.me();
        if (alive) {
          setUser(me);
          setStatus('signedIn');
        }
      } catch {
        if (alive) await signOutLocally();
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, tokens, signOutLocally]);

  useEffect(() => {
    const unsubscribe = onSessionExpired(() => {
      void signOutLocally();
    });
    return () => {
      unsubscribe();
    };
  }, [signOutLocally]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email.trim(), password);
    await tokens.setTokens(res.tokens);
    setUser(res.user);
    setStatus('signedIn');
  }, [api, tokens]);

  const register = useCallback<AuthState['register']>(async (body) => {
    const res = await api.register({ ...body, email: body.email.trim() });
    await tokens.setTokens(res.tokens);
    setUser(res.user);
    setStatus('signedIn');
  }, [api, tokens]);

  const logout = useCallback(async () => {
    const refresh = await tokens.getRefresh();
    if (refresh) {
      try {
        await api.logout(refresh);
      } catch {
        // Already invalid: nothing to revoke.
      }
    }
    await signOutLocally();
  }, [api, tokens, signOutLocally]);

  const refreshUser = useCallback(async () => {
    setUser(await api.me());
  }, [api]);

  const value = useMemo<AuthState>(() => ({
    status, user, role: user?.role ?? null, login, register, logout, refreshUser,
  }), [status, user, login, register, logout, refreshUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
