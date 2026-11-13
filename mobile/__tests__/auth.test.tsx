import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { AxiosError, AxiosResponse } from 'axios';
import React from 'react';
import { Text } from 'react-native';

import type { TokenStore } from '../src/api/client';
import { AuthProvider, useAuth } from '../src/auth/AuthContext';
import { LoginScreen } from '../src/screens/auth';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async () => null), setItemAsync: jest.fn(), deleteItemAsync: jest.fn(),
}));

const user = { id: 1, email: 'thandi@example.com', role: 'FARMER', display_name: 'Thandi', phone_number: '',
  created_at: '', updated_at: '' };

function setup(login: jest.Mock) {
  const saved: Record<string, string> = {};
  const tokens: TokenStore = {
    getAccess: async () => saved.access ?? null,
    getRefresh: async () => saved.refresh ?? null,
    setTokens: async (t) => { saved.access = t.access; if (t.refresh) saved.refresh = t.refresh; },
    clear: async () => { delete saved.access; delete saved.refresh; },
  };
  const api = { login, register: jest.fn(), logout: jest.fn(), me: jest.fn(async () => user) };
  function Status() {
    const { status, user: u } = useAuth();
    return <Text testID="status">{status}:{u?.display_name ?? ''}</Text>;
  }
  const navigation = { navigate: jest.fn() } as never;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider tokens={tokens} api={api as never}>
        <Status />
        <LoginScreen navigation={navigation} route={{ key: 'Login', name: 'Login' } as never} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { saved };
}

test('logs in, stores tokens securely and switches to signed in', async () => {
  const login = jest.fn(async () => ({ user, role: 'FARMER', tokens: { access: 'A', refresh: 'R' } }));
  const { saved } = setup(login);
  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signedOut:'));

  fireEvent.changeText(screen.getByLabelText('Email'), ' thandi@example.com ');
  fireEvent.changeText(screen.getByLabelText('Password'), 'secret-pass');
  fireEvent.press(screen.getByRole('button', { name: 'Log in' }));

  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signedIn:Thandi'));
  expect(login).toHaveBeenCalledWith('thandi@example.com', 'secret-pass');
  expect(saved).toEqual({ access: 'A', refresh: 'R' });
});

test('shows validation errors before calling the API', async () => {
  const login = jest.fn();
  setup(login);
  fireEvent.press(await screen.findByRole('button', { name: 'Log in' }));
  expect(await screen.findByText('Enter a valid email address')).toBeTruthy();
  expect(screen.getByText('Enter your password')).toBeTruthy();
  expect(login).not.toHaveBeenCalled();
});

test('shows a friendly message for wrong credentials', async () => {
  const response = { status: 401, data: { error: { code: 'authentication_failed', message: 'No active account',
    details: {} } } } as AxiosResponse;
  const login = jest.fn(async () => { throw new AxiosError('401', '401', undefined, null, response); });
  setup(login);
  fireEvent.changeText(await screen.findByLabelText('Email'), 'thandi@example.com');
  fireEvent.changeText(screen.getByLabelText('Password'), 'wrong');
  fireEvent.press(screen.getByRole('button', { name: 'Log in' }));
  expect(await screen.findByText('Wrong email or password.')).toBeTruthy();
  expect(screen.getByTestId('status')).toHaveTextContent('signedOut:');
});
